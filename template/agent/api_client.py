import requests
import json
import uuid
from typing import List, Dict, Optional
from os import environ
from dotenv import load_dotenv
from datetime import datetime
from template.configs.environments import env

load_dotenv()

class APIClient:
    """Client để gửi thông tin plan và task status lên Planner API server"""
    
    def __init__(self):
        self.base_url = env.PLAN_API_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.current_plan_id = None
        self.current_task_ids = {}  # mapping task title -> task_id
        self.session_id = 1
    
    def create_plan(self, plan_data: Dict) -> Optional[Dict]:
        """
        Tạo plan mới với các tasks
        
        Args:
            plan_data: Dictionary chứa thông tin plan
            {
                "input": str,
                "plan_type": str,
                "current_plan": List[str],
                "status": str
            }
        """
        try:
            # Chuyển đổi current_plan thành tasks format
            tasks = []
            for index, task_title in enumerate(plan_data.get("current_plan", [])):
                tasks.append({
                    "order_no": index + 1,
                    "title": task_title,
                    "description": f"Task từ {plan_data.get('plan_type', 'unknown')} plan",
                    "max_retries": 2
                })
            
            # Tạo plan payload theo format API
            plan_payload = [{
                "session_id": self.session_id,
                "title": f"Plan Agent - {plan_data.get('plan_type', 'Unknown').title()}",
                "goal_text": plan_data.get("input", ""),
                "trigger": "SYSTEM",
                "priority": 1,
                "tasks": tasks
            }]
            
            response = self.session.post(
                f"{self.base_url}/api/v1/plans",
                json=plan_payload
            )
            response.raise_for_status()
            
            result = response.json()
            # Lưu plan_id và task_ids để sử dụng sau
            if result.get("data", {}).get("insert_planner_plans", {}).get("returning"):
                plan = result["data"]["insert_planner_plans"]["returning"][0]
                self.current_plan_id = plan["id"]
                
                # Lưu mapping task title -> task_id
                for task in plan.get("tasks", []):
                    self.current_task_ids[task["title"]] = task["id"]
                
                print(f"✅ Created plan with ID: {self.current_plan_id}")
            
            return result
        except requests.exceptions.RequestException as e:
            print(f"❌ Error creating plan: {e}")
            return None
    
    def update_plan_status(self, status: str, goal_text: str = None) -> Optional[Dict]:
        """
        Cập nhật status của plan
        
        Args:
            status: "created", "in_progress", "completed", "failed"
            goal_text: Updated goal text (optional)
        """
        if not self.current_plan_id:
            print("❌ No current plan ID to update")
            return None
            
        try:
            payload = {"status": status}
            if goal_text:
                payload["goal_text"] = goal_text
                
            response = self.session.put(
                f"{self.base_url}/api/v1/plans/{self.current_plan_id}",
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            print(f"✅ Updated plan status to: {status}")
            return result
        except requests.exceptions.RequestException as e:
            print(f"❌ Error updating plan status: {e}")
            return None
    
    def update_task_status(self, task_title: str, status: str, execution_result: str = None) -> Optional[Dict]:
        """
        Cập nhật status của task
        
        Args:
            task_title: Tên của task
            status: "pending", "in_progress", "completed", "failed"
            execution_result: Kết quả thực thi task
        """
        task_id = self.current_task_ids.get(task_title)
        if not task_id:
            print(f"❌ No task ID found for task: {task_title}")
            return None
            
        try:
            payload = {"status": status}
            if execution_result:
                payload["execution_result"] = execution_result
                
            response = self.session.put(
                f"{self.base_url}/api/v1/tasks/{task_id}",
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            print(f"✅ Updated task '{task_title}' status to: {status}")
            return result
        except requests.exceptions.RequestException as e:
            print(f"❌ Error updating task status: {e}")
            return None
    
    def get_plan(self, plan_id: str = None) -> Optional[Dict]:
        """Lấy thông tin plan"""
        plan_id = plan_id or self.current_plan_id
        if not plan_id:
            print("❌ No plan ID provided")
            return None
            
        try:
            response = self.session.get(f"{self.base_url}/api/v1/plans/{plan_id}")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Error getting plan: {e}")
            return None
    
    def get_all_plans(self) -> Optional[Dict]:
        """Lấy tất cả plans"""
        try:
            response = self.session.get(f"{self.base_url}/api/v1/plans")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Error getting all plans: {e}")
            return None
    
    # Backward compatibility methods
    def send_plan_status(self, plan_data: Dict) -> Optional[Dict]:
        """Compatibility method - tạo plan hoặc update status"""
        status = plan_data.get("status", "created")
        
        if status == "plan_created":
            return self.create_plan(plan_data)
        elif status == "execution_started":
            return self.update_plan_status("in_progress")
        elif status == "plan_updated":
            return self.update_plan_status("in_progress")
        else:
            return self.update_plan_status(status)
    
    def send_task_update(self, task_data: Dict) -> Optional[Dict]:
        """Compatibility method - update task"""
        task_name = task_data.get("task_name", "")
        task_status = "completed" if task_data.get("status") == "task_completed" else "in_progress"
        execution_result = task_data.get("task_response", "")
        
        return self.update_task_status(task_name, task_status, execution_result)
    
    def send_final_result(self, result_data: Dict) -> Optional[Dict]:
        """Compatibility method - finalize plan"""
        return self.update_plan_status("completed", result_data.get("final_answer"))