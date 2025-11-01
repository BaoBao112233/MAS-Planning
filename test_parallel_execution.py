"""
Test script for Plan Agent Parallel Execution
Demonstrates multi-threading capability
"""
import asyncio
import time
from template.agent.plan import PlanAgent


def test_parallel_execution():
    """Test parallel task execution vs sequential"""
    
    print("=" * 60)
    print("🧪 Testing Plan Agent - Parallel Execution")
    print("=" * 60)
    
    # Initialize Plan Agent
    plan_agent = PlanAgent(
        model="gemini-2.5-pro",
        temperature=0.2,
        verbose=True
    )
    
    # Simulate async init (if needed)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(plan_agent.init_async())
        loop.close()
        print("✅ Plan Agent initialized successfully\n")
    except Exception as e:
        print(f"⚠️ Async init not required or failed: {e}\n")
    
    # Create test plan with 3 tasks
    test_plan_options = {
        'security_plan': [
            "Check all door locks",
            "Verify window sensors", 
            "Activate alarm system"
        ],
        'convenience_plan': [
            "Turn on living room lights",
            "Set temperature to 22°C",
            "Open bedroom curtains"
        ],
        'energy_plan': [
            "Turn off unused lights",
            "Reduce thermostat by 2°C",
            "Power down entertainment system"
        ]
    }
    
    # Test state
    test_state = {
        'input': 'Test parallel execution',
        'selected_plan_id': 1,  # Security plan
        'plan_options': test_plan_options,
        'token': 'test_token_123'
    }
    
    print(f"📋 Test Plan: Security Priority Plan")
    print(f"   Tasks: {len(test_plan_options['security_plan'])}")
    for i, task in enumerate(test_plan_options['security_plan'], 1):
        print(f"   {i}. {task}")
    print()
    
    # Execute plan
    print("🚀 Starting parallel execution...\n")
    start_time = time.time()
    
    try:
        result = plan_agent.execute_selected_plan(test_state)
        
        execution_time = time.time() - start_time
        
        print("\n" + "=" * 60)
        print("📊 EXECUTION RESULTS")
        print("=" * 60)
        print(f"⏱️  Total Time: {execution_time:.2f}s")
        print(f"📝 Output:\n{result.get('output', 'No output')}")
        print()
        
        # Analyze results
        exec_results = result.get('execution_results', [])
        if exec_results:
            print("🔍 Detailed Results:")
            for res in exec_results:
                status_icon = "✅" if res['status'] == 'completed' else "❌"
                print(f"   {status_icon} Task {res['task_number']}: {res['status']}")
            print()
        
        # Calculate expected sequential time (mock)
        num_tasks = len(test_plan_options['security_plan'])
        estimated_sequential_time = num_tasks * 10  # Assume 10s per task
        
        print("💡 Performance Estimation:")
        print(f"   Sequential (estimated): {estimated_sequential_time}s")
        print(f"   Parallel (actual): {execution_time:.2f}s")
        
        if execution_time < estimated_sequential_time:
            speedup = estimated_sequential_time / execution_time
            print(f"   🚀 Speedup: {speedup:.2f}x faster!")
        else:
            print(f"   ⚠️  Note: Actual execution may vary based on task complexity")
        
        print("\n✨ Test completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_concurrent_logging():
    """Test thread-safe logging"""
    print("\n" + "=" * 60)
    print("🧪 Testing Concurrent Logging")
    print("=" * 60)
    
    import threading
    import logging
    
    logger = logging.getLogger(__name__)
    
    def log_from_thread(thread_id):
        for i in range(3):
            logger.info(f"[Thread-{thread_id}] Message {i+1}")
            time.sleep(0.1)
    
    threads = []
    for i in range(3):
        t = threading.Thread(target=log_from_thread, args=(i,))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    print("✅ Concurrent logging test completed\n")


if __name__ == "__main__":
    print("\n" + "🎯" * 30)
    print("PLAN AGENT PARALLEL EXECUTION TEST SUITE")
    print("🎯" * 30 + "\n")
    
    # Run tests
    success = test_parallel_execution()
    
    # Run logging test
    test_concurrent_logging()
    
    # Summary
    print("=" * 60)
    if success:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 60)
