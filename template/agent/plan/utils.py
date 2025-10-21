import re

def extract_plan(response):
    extracted_data = {}
    # Check if it's Option 1 (gathering information)
    option1_match = re.search(r'<option>\s*<question>(.*?)</question>\s*<answer>(.*?)</answer>\s*<route>(.*?)</route>\s*</option>', response, re.DOTALL)
    if option1_match:
        extracted_data['Question'] = option1_match.group(1).strip()
        extracted_data['Answer'] = option1_match.group(2).strip()
        extracted_data['Route'] = option1_match.group(3).strip()
        return extracted_data

    # Check if it's Option 2 (providing the final plan)
    option2_match = re.search(r'<option>\s*<plan>(.*?)</plan>\s*<route>(.*?)</route>\s*</option>', response, re.DOTALL)
    if option2_match:
        # Extract each task from the plan
        plan_content = option2_match.group(1).strip()
        tasks = re.findall(r'(\d+)\.\s*(.*)', plan_content)
        extracted_data['Plan'] = [task[1].strip() for task in tasks]
        extracted_data['Route'] = option2_match.group(2).strip()
        return extracted_data

def extract_llm_response(xml_response: str) -> dict:
    # Initialize the result dictionary
    result = {
        'Current Plan': None,
        'Pending': None,
        'Completed': None,
        'Final Answer': None,
        'Route': None
    }
    
    # Define regex patterns to match each part of the response
    current_plan_regex = re.compile(r'<current-plan>\s*(.*?)\s*</current-plan>', re.DOTALL)
    pending_regex = re.compile(r'<pending>\s*(.*?)\s*</pending>', re.DOTALL)
    completed_regex = re.compile(r'<completed>\s*(.*?)\s*</completed>', re.DOTALL)
    final_answer_regex = re.compile(r'<final-answer>\s*(.*?)\s*</final-answer>', re.DOTALL)
    route_regex = re.compile(r'<route>\s*(.*?)\s*</route>', re.DOTALL)

    # Helper function to clean up task lists by removing bullet points, dashes, and extra characters
    def clean_task_list(task_string: str) -> list:
        # Remove the bullet markers like '- [ ]', '- [x]', and any extra dashes or spaces
        cleaned_tasks = re.sub(r'[-–]\s*\[\s*\]|\[\s*x\s*\]|[-–]\s*', '', task_string)
        # Split the cleaned tasks into a list and strip unnecessary spaces
        return [task.strip() for task in cleaned_tasks.split('\n') if task.strip()]

    # Extract Current Plan
    current_plan_match = current_plan_regex.search(xml_response)
    if current_plan_match:
        current_plan_content = current_plan_match.group(1).strip()
        # Remove numeric prefixes like "1.", "2.", etc.
        result['Current Plan'] = [re.sub(r'^\d+\.\s*', '', task).strip() for task in current_plan_content.split('\n') if task.strip()]

    # Extract Pending tasks
    pending_match = pending_regex.search(xml_response)
    if pending_match:
        pending_content = pending_match.group(1).strip()
        result['Pending'] = clean_task_list(pending_content)

    # Extract Completed tasks
    completed_match = completed_regex.search(xml_response)
    if completed_match:
        completed_content = completed_match.group(1).strip()
        result['Completed'] = clean_task_list(completed_content)

    # Extract Final Answer
    final_answer_match = final_answer_regex.search(xml_response)
    if final_answer_match:
        result['Final Answer'] = final_answer_match.group(1).strip()

    # Extract Route
    route_match = route_regex.search(xml_response)
    if route_match:
        result['Route'] = route_match.group(1).strip()

    return result

def extract_priority_plans(response):
    """Extract the 3 priority plans from priority_plan.md response"""
    extracted_data = {
        'Security_Plan': [],
        'Convenience_Plan': [],
        'Energy_Plan': []
    }
    
    # Split response into lines for easier processing
    lines = response.split('\n')
    current_plan = None
    
    for line in lines:
        line = line.strip()
        
        # Look for plan headers
        if "Plan 1:" in line or "Maximum Security" in line or "🥇" in line:
            current_plan = 'Security_Plan'
        elif "Plan 2:" in line or "Balanced Comfort" in line or "🥈" in line:
            current_plan = 'Convenience_Plan'
        elif "Plan 3:" in line or "Energy-Efficient" in line or "🥉" in line:
            current_plan = 'Energy_Plan'
        # Look for numbered tasks
        elif current_plan and re.match(r'^\d+\.', line):
            # Extract task text (remove number prefix)
            task = re.sub(r'^\d+\.\s*', '', line)
            if task:  # Only add non-empty tasks
                extracted_data[current_plan].append(task)
    
    # If we couldn't find the specific headers, try alternative parsing
    if not any(extracted_data.values()):
        # Try to find tasks under any plan structure
        plan_patterns = [
            (r'(?:plan\s+1|security|🥇).*?(?=plan\s+2|convenience|🥈|$)', 'Security_Plan'),
            (r'(?:plan\s+2|convenience|🥈).*?(?=plan\s+3|energy|🥉|$)', 'Convenience_Plan'),
            (r'(?:plan\s+3|energy|🥉).*?(?=plan\s+4|custom|$)', 'Energy_Plan')
        ]
        
        for pattern, plan_key in plan_patterns:
            match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
            if match:
                plan_text = match.group(0)
                tasks = re.findall(r'(\d+)\.\s*(.*)', plan_text)
                extracted_data[plan_key] = [task[1].strip() for task in tasks if task[1].strip()]
    
    return extracted_data

def read_markdown_file(file_path: str) -> str:
    with open(file_path, 'r',encoding='utf-8') as f:
        markdown_content = f.read()
    return markdown_content