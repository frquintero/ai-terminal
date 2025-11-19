from ui_formatter import UIFormatter
from rich.console import Console
from rich.markdown import Markdown

console = Console()
formatter = UIFormatter()

content = """Here's a Python script for calculating the nth term of the Fibonacci series:

```python
def fibonacci(n):
    \"\"\"
    Calculate the nth term in the Fibonacci series.

    Args:
        n (int): The position in the Fibonacci sequence (0-indexed)

    Returns:
        int: The nth Fibonacci number
    \"\"\"
    if n < 0:
        raise ValueError("n must be a non-negative integer")
    elif n <= 1:
        return n
    else:
        # Use iterative approach for better performance
        a, b = 0, 1
        for _ in range(2, n + 1):
            a, b = b, a + b
        return b

# Example usage
if __name__ == "__main__":
    # Calculate some terms
    for i in range(11):
        print(f"F({i}) = {fibonacci(i)}")

    # Calculate the 10th term specifically
    nth_term = fibonacci(10)
    print(f"\\nThe 10th term in the Fibonacci series is: {nth_term}")
```

This script includes:

1. **Efficient iterative approach** - Instead of recursive calls, it uses iteration which is much faster and doesn't risk stack overflow
2. **Input validation** - Checks for negative inputs
3. **Clear documentation** - Includes docstring and comments
4. **Example usage** - Shows how to use the function and prints the first 11 terms

The iterative approach runs in O(n) time with O(1) space complexity, making it much more efficient than the recursive version.
"""

print("--- Rendering Markdown ---")
console.print(formatter._create_markdown(content))
