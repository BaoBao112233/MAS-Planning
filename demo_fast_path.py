#!/usr/bin/env python3
"""
Quick Demo: Fast-Path Classification System
Shows how to use the classifier and interpret results
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from template.agent.manager.fast_path import (
    get_fast_path_classifier,
    IntentClass,
    ExecutionPath
)
from termcolor import colored


def demo_basic_usage():
    """Demo: Basic classification usage"""
    print(colored("\n📘 DEMO 1: Basic Usage", "cyan", attrs=["bold"]))
    print("=" * 80)
    
    # Get classifier
    classifier = get_fast_path_classifier(verbose=False)
    
    # Example queries
    queries = [
        "Bật đèn phòng khách",
        "Show me all devices",
        "Tạo kế hoạch automation",
        "Hello"
    ]
    
    for query in queries:
        print(f"\n🔍 Query: '{query}'")
        result = classifier.classify(query)
        
        if result:
            print(f"   Intent: {colored(result.intent.value, 'green')}")
            print(f"   Path: {colored(result.execution_path.value, 'yellow')}")
            print(f"   Confidence: {result.confidence:.0%}")


def demo_device_control():
    """Demo: Device control routing"""
    print(colored("\n📘 DEMO 2: Device Control (Tool → Manager)", "cyan", attrs=["bold"]))
    print("=" * 80)
    
    classifier = get_fast_path_classifier(verbose=False)
    
    query = "Bật đèn phòng khách"
    result = classifier.classify(query)
    
    print(f"\n🔍 Query: '{query}'")
    print(f"   Intent: {result.intent.value}")
    print(f"   Execution Path: {result.execution_path.value}")
    print(f"   Params: {result.extracted_params}")
    
    print(colored("\n🔄 Routing Flow:", "yellow", attrs=["bold"]))
    print("   1. ➡️  Tool Agent executes command")
    print("   2. ➡️  Manager analyzes result (< 1s)")
    print("   3. ➡️  Return to user")


def demo_show_devices():
    """Demo: Show device status (Manager only)"""
    print(colored("\n📘 DEMO 3: Show Devices (Manager Only)", "cyan", attrs=["bold"]))
    print("=" * 80)
    
    classifier = get_fast_path_classifier(verbose=False)
    
    query = "Show me all devices"
    result = classifier.classify(query)
    
    print(f"\n🔍 Query: '{query}'")
    print(f"   Intent: {result.intent.value}")
    print(f"   Execution Path: {result.execution_path.value}")
    
    print(colored("\n🔄 Routing Flow:", "yellow", attrs=["bold"]))
    print("   1. ➡️  Manager calls get_device_list tool")
    print("   2. ➡️  Manager formats response (< 1s)")
    print("   3. ➡️  Return to user")
    print(colored("   ⚠️  NO Tool Agent call needed!", "red"))
    
    # Demo formatting
    print(colored("\n📄 Sample Output Format:", "green"))
    mock_device_list = {
        'data': {
            'rooms': [{
                'roomName': 'Phòng khách',
                'devices': [{
                    'deviceName': 'Đèn trần',
                    'deviceStatus': True,
                    'buttons': [
                        {'buttonName': 'Nút 1', 'buttonStatus': True},
                        {'buttonName': 'Nút 2', 'buttonStatus': False}
                    ]
                }]
            }]
        }
    }
    
    formatted = classifier.format_device_status_response(
        mock_device_list,
        result.extracted_params
    )
    print(formatted)


def demo_planning():
    """Demo: Planning workflow"""
    print(colored("\n📘 DEMO 4: Planning (Full Workflow)", "cyan", attrs=["bold"]))
    print("=" * 80)
    
    classifier = get_fast_path_classifier(verbose=False)
    
    query = "Tạo kế hoạch automation cho phòng ngủ"
    result = classifier.classify(query)
    
    print(f"\n🔍 Query: '{query}'")
    print(f"   Intent: {result.intent.value}")
    print(f"   Execution Path: {result.execution_path.value}")
    
    print(colored("\n🔄 Routing Flow:", "yellow", attrs=["bold"]))
    print("   1. ➡️  Manager analyzes request (< 1s)")
    print("   2. ➡️  Plan Agent creates 2 plans")
    print("   3. ⏸️  Wait for user to select plan")
    print("   4. ➡️  Tool Agent executes selected plan")
    print("   5. ➡️  Manager analyzes results (< 1s)")
    print("   6. ➡️  Return to user")


def demo_unknown():
    """Demo: Unknown query handling"""
    print(colored("\n📘 DEMO 5: Unknown Query (Manager Direct)", "cyan", attrs=["bold"]))
    print("=" * 80)
    
    classifier = get_fast_path_classifier(verbose=False)
    
    query = "Hello, how are you?"
    result = classifier.classify(query)
    
    print(f"\n🔍 Query: '{query}'")
    print(f"   Intent: {result.intent.value}")
    print(f"   Execution Path: {result.execution_path.value}")
    print(f"   Confidence: {result.confidence:.0%}")
    
    print(colored("\n🔄 Routing Flow:", "yellow", attrs=["bold"]))
    print("   1. ➡️  Manager generates direct response (< 1s)")
    print("   2. ➡️  Return to user")
    print(colored("   ⚠️  NO delegation to other agents!", "red"))


def demo_performance():
    """Demo: Performance metrics"""
    print(colored("\n📘 DEMO 6: Performance Metrics", "cyan", attrs=["bold"]))
    print("=" * 80)
    
    import time
    classifier = get_fast_path_classifier(verbose=False)
    
    test_cases = [
        ("Device Control", "Bật đèn phòng khách"),
        ("Show Devices", "Show all devices"),
        ("Planning", "Create automation plan"),
        ("Unknown", "Hello")
    ]
    
    print("\n⏱️  Classification Performance:")
    print("-" * 80)
    
    for name, query in test_cases:
        start = time.time()
        result = classifier.classify(query)
        elapsed = (time.time() - start) * 1000  # ms
        
        status = "✅" if elapsed < 100 else "⚠️"
        print(f"{status} {name:20s} | {elapsed:6.2f}ms | {result.intent.value}")
    
    print("\n🎯 Target: < 100ms per classification")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print(colored("  FAST-PATH CLASSIFICATION SYSTEM - QUICK DEMO", "white", "on_blue", attrs=["bold"]))
    print("=" * 80)
    
    # Run all demos
    demo_basic_usage()
    demo_device_control()
    demo_show_devices()
    demo_planning()
    demo_unknown()
    demo_performance()
    
    print("\n" + "=" * 80)
    print(colored("  🎉 DEMO COMPLETE!", "green", attrs=["bold"]))
    print("=" * 80)
    print("\n📚 For full documentation, see: docs/FAST_PATH_CLASSIFICATION.md")
    print("🧪 For comprehensive tests, run: test_folders/test_fast_path_classification.py\n")
