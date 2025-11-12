"""
Router CLI Tool - Manual testing and debugging of route classification

Usage:
    python -m router.cli "What is Docker?"
    python -m router.cli "ls -la" --verbose
    python -m router.cli "Create a monitoring script" --show-patterns
    python -m router.cli "history" --cache-threshold 0.85
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from router.router import Router
from memory.api import Memory


def print_header(title: str, width: int = 80) -> None:
    """Print formatted header."""
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}\n")


def print_result(result: dict, verbose: bool = False, show_patterns: bool = False) -> None:
    """Pretty-print routing result."""
    print(f"Query: {result['query']}")
    print(f"Route: {result['route']} (confidence: {result['confidence']:.2f})")
    
    if result.get("matched_rule"):
        print(f"Matched Rule: {result['matched_rule']}")
    
    if result.get("cache_hit"):
        print(f"\n📦 Cache Hit:")
        print(f"   Tool: {result['cache_hit']['tool_name']}")
        print(f"   Args: {json.dumps(result['cache_hit']['tool_args'], indent=2)}")
        print(f"   Score: {result['cache_hit']['score']:.3f}")
    
    if verbose:
        print(f"\nDetailed Analysis:")
        print(f"  Is interactive: {result.get('is_interactive', False)}")
        print(f"  Rules matched: {result.get('rules_matched', [])}")
    
    if show_patterns:
        print(f"\nPattern Statistics:")
        print(f"  Shell patterns checked: {result.get('shell_patterns_count', 0)}")
        print(f"  Chat patterns checked: {result.get('chat_patterns_count', 0)}")
        print(f"  Interactive patterns checked: {result.get('interactive_patterns_count', 0)}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Router CLI - Test query classification and debugging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Simple classification
  python -m router.cli "What is Docker?"
  
  # With verbose output
  python -m router.cli "ls -la" --verbose
  
  # Show matched patterns
  python -m router.cli "Create a script" --show-patterns
  
  # Test cache with custom threshold
  python -m router.cli "list files" --cache-threshold 0.85
  
  # Batch test from file
  python -m router.cli --test-file test_queries.txt
  
  # Interactive mode
  python -m router.cli --interactive
        """,
    )
    
    parser.add_argument(
        "query",
        nargs="?",
        help="User query to classify",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed analysis",
    )
    parser.add_argument(
        "--show-patterns",
        action="store_true",
        help="Show matched patterns and statistics",
    )
    parser.add_argument(
        "--cache-threshold",
        type=float,
        default=0.85,
        help="Cache hit threshold (0.0-1.0, default: 0.85)",
    )
    parser.add_argument(
        "--test-file",
        type=str,
        help="Load test queries from file (one per line)",
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Interactive mode (read queries from stdin)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show router statistics",
    )
    parser.add_argument(
        "--database",
        type=str,
        default=None,
        help="Path to memory database (default: logs/orchestrator.db)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    
    args = parser.parse_args()
    
    # Initialize router and memory
    router = Router(memory=Memory(db_path=Path(args.database) if args.database else None))
    
    # Show stats if requested
    if args.stats:
        print_header("Router Statistics")
        stats = router.rule_engine.get_stats()
        print(json.dumps(stats, indent=2))
        return 0
    
    # Batch test from file
    if args.test_file:
        return batch_test(router, args.test_file, args.verbose, args.json)
    
    # Interactive mode
    if args.interactive:
        return interactive_mode(router, args.verbose)
    
    # Single query mode
    if not args.query:
        parser.print_help()
        return 1
    
    result = classify_query(router, args.query, args.verbose, args.show_patterns)
    
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_result(result, verbose=args.verbose, show_patterns=args.show_patterns)
    
    return 0


def classify_query(router: Router, query: str, verbose: bool = False, show_patterns: bool = False) -> dict:
    """Classify a single query and return result dict."""
    router_result = router.classify(query)
    
    result = {
        "query": query,
        "route": router_result.route.value,
        "confidence": router_result.confidence,
        "matched_rule": router_result.matched_rule,
        "cache_hit": None,
        "is_interactive": router.rule_engine.is_interactive_command(query),
        "shell_patterns_count": len(router.rule_engine.shell_patterns),
        "chat_patterns_count": len(router.rule_engine.chat_patterns),
        "interactive_patterns_count": len(router.rule_engine.interactive_patterns),
    }
    
    # Add cache info if CACHED route
    if router_result.route.value == "CACHED" and hasattr(router_result, "cache_hit"):
        result["cache_hit"] = router_result.cache_hit
    
    return result


def batch_test(router: Router, test_file: str, verbose: bool = False, json_output: bool = False) -> int:
    """Test multiple queries from file."""
    try:
        with open(test_file, 'r') as f:
            queries = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except FileNotFoundError:
        print(f"Error: File not found: {test_file}", file=sys.stderr)
        return 1
    
    print_header(f"Batch Testing ({len(queries)} queries)")
    
    results = []
    route_counts = {}
    
    for i, query in enumerate(queries, 1):
        result = classify_query(router, query, verbose)
        results.append(result)
        
        route = result["route"]
        route_counts[route] = route_counts.get(route, 0) + 1
        
        if not json_output:
            print(f"{i}. [{result['route']:8}] (conf: {result['confidence']:.2f}) {query[:60]}")
    
    # Summary
    print_header("Summary")
    for route, count in sorted(route_counts.items()):
        percentage = (count / len(queries)) * 100
        print(f"  {route:10} {count:3} queries ({percentage:5.1f}%)")
    
    if json_output:
        print(json.dumps(results, indent=2))
    
    return 0


def interactive_mode(router: Router, verbose: bool = False) -> int:
    """Interactive REPL for testing queries."""
    print_header("Router CLI - Interactive Mode")
    print("Commands:")
    print("  Type a query to classify it")
    print("  Type 'stats' to show statistics")
    print("  Type 'help' for help")
    print("  Type 'quit' or Ctrl+D to exit")
    print()
    
    try:
        while True:
            try:
                query = input("query> ").strip()
            except EOFError:
                print("\nGoodbye!")
                return 0
            
            if not query:
                continue
            
            if query.lower() == "quit":
                print("Goodbye!")
                return 0
            
            if query.lower() == "stats":
                stats = router.rule_engine.get_stats()
                print(json.dumps(stats, indent=2))
                continue
            
            if query.lower() == "help":
                print("Commands:")
                print("  <query>  Classify the query")
                print("  stats    Show router statistics")
                print("  help     Show this help")
                print("  quit     Exit")
                continue
            
            result = classify_query(router, query, verbose)
            print_result(result, verbose=verbose)
    
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
