#!/usr/bin/env python3
"""Test working directory isolation for file operations"""

import os
import sys
from tools import TOOLS, WORKING_DIR_PREFIX, _get_working_dir_path

def test_write_file():
    """Test that write_file creates files in isolated directory"""
    print("=" * 80)
    print("TESTING WRITE_FILE ISOLATION")
    print("=" * 80)
    
    # Get the write_file tool
    write_tool = TOOLS.get("write_file")
    
    # Test file content
    js_code = """// Counter from 1 to 10
for (let i = 1; i <= 10; i++) {
    console.log(i);
}
"""
    
    # Execute write_file with relative path (no prefix)
    print(f"\n📝 Executing: write_file(file_path='counter.js', content=...)")
    result = write_tool.execute(file_path="counter.js", content=js_code)
    print(f"Result: {result}")
    
    # Verify file location
    expected_path = os.path.join(_get_working_dir_path(), "counter.js")
    print(f"\n🔍 Expected file location: {expected_path}")
    
    if os.path.exists(expected_path):
        print(f"✅ File created successfully in isolated directory!")
        with open(expected_path, 'r') as f:
            content = f.read()
        print(f"\n📄 File contents:\n{content}")
    else:
        print(f"❌ File NOT found at expected location!")
        return False
    
    # Test read_file
    print("\n" + "=" * 80)
    print("TESTING READ_FILE ISOLATION")
    print("=" * 80)
    
    read_tool = TOOLS.get("read_file")
    print(f"\n📖 Executing: read_file(file_path='counter.js')")
    read_result = read_tool.execute(file_path="counter.js")
    print(f"Result:\n{read_result}")
    
    # Test with subdirectory
    print("\n" + "=" * 80)
    print("TESTING SUBDIRECTORY")
    print("=" * 80)
    
    print(f"\n📝 Executing: write_file(file_path='scripts/test.js', content=...)")
    subdir_result = write_tool.execute(file_path="scripts/test.js", content="console.log('test');")
    print(f"Result: {subdir_result}")
    
    expected_subdir_path = os.path.join(_get_working_dir_path(), "scripts", "test.js")
    print(f"\n🔍 Expected file location: {expected_subdir_path}")
    
    if os.path.exists(expected_subdir_path):
        print(f"✅ Subdirectory file created successfully!")
    else:
        print(f"❌ Subdirectory file NOT found!")
        return False
    
    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED")
    print("=" * 80)
    return True

if __name__ == "__main__":
    try:
        success = test_write_file()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
