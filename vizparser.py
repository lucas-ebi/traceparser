import json
import argparse
from collections import defaultdict
import re
import graphviz
import hashlib
import networkx as nx

def load_json_data(file_path):
    """
    Load and return the JSON data from the given file path.
    """
    try:
        with open(file_path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"Error: The file {file_path} was not found.")
        exit(1)
    except json.JSONDecodeError:
        print(f"Error: Failed to parse JSON from {file_path}.")
        exit(1)

def format_function_call(input_str):
    # Initialize variables
    function_name = None
    file_path = None
    line = None

    # Use regex to extract the function name, file path, and line number
    match = re.search(r"(.+) \(([^:()]+(?![^()]*[<>])):(\d+)\)", input_str)
    if match:
        function_name, file_path, line = match.groups()

    if any(char in function_name for char in ["<", ">"]):
        function_name = None

    # Proceed only if function_name is successfully extracted and does not contain "<" or ">"
    if file_path:
        # Define the regex pattern to split by, which matches "py-wwpdb_" followed by any string and a "/"
        pattern = r"py-wwpdb_[^/]+/"

        # Extract the substring that matches the pattern
        match = re.search(pattern, file_path)
        if match:
            # Extract the matched substring
            repository = match.group(0)
            # Use the matched substring to split the file path
            file_path = file_path.split(repository)[1]

    return function_name, file_path, line

def hash_string_to_rgb(input_str):
    """
    Hash a string to an RGB color.
    """
    hash_object = hashlib.md5(input_str.encode())
    hash_hex = hash_object.hexdigest()
    # Use the first 6 characters of the hash to create an RGB value
    rgb = tuple(int(hash_hex[i:i+2], 16) for i in (0, 2, 4))
    return f'#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}'

def process_events(data):
    events = data if isinstance(data, list) else data.get('traceEvents', [])
    filtered_events = [event for event in events if 'ts' in event and event['ph'] == 'X']
    sorted_events = sorted(filtered_events, key=lambda x: x['ts'])

    event_stack = []  # Stack to keep track of the call hierarchy
    dependency_graph = defaultdict(set)  # Initialize the dependency graph

    for i, event in enumerate(sorted_events):
        event_end = event['ts'] + event.get('dur', 0)

        # Pop events from the stack that have ended
        while event_stack and event_stack[-1]['end'] <= event['ts']:
            popped_event = event_stack.pop()
            if event_stack:  # If there's a caller, update the graph
                caller, caller_path, caller_line = format_function_call(event_stack[-1]['name'])
                callee, callee_path, callee_line = format_function_call(popped_event['name'])
                if caller and callee:
                    source = f"name={caller}\nfile={caller_path}\nline={caller_line}"
                    target = f"name={callee}\nfile={callee_path}\nline={callee_line}"
                    dependency_graph[source].add(target)

        # Determine the indentation
        indent = ''.join(['|   ' for _ in range(len(event_stack))])

        # Check if the current event is the last one at its depth
        is_last_at_depth = True  # Assume it's the last by default
        if i + 1 < len(sorted_events):
            next_event_start = sorted_events[i + 1]['ts']
            is_last_at_depth = not (next_event_start < event_end or len(event_stack) == len(sorted_events[i + 1].get('stack', [])))

        # Adjust branch symbol based on whether it's the last event at its depth
        branch_symbol = '└─ ' if is_last_at_depth else '├─ '

        input_str = event['name']
        call, path, line = format_function_call(input_str)
        formatted_str = f"{call} ({path}:{line})" if call else None
        if formatted_str:
            print(f"{indent}{branch_symbol}{formatted_str}")

        event['end'] = event_end
        event_stack.append(event)
    
    print(f"└─-{2*len(indent)*'-'}-END")  # Print the end of the call stack
    
    return dependency_graph  # Return the graph for visualization

def extract_file_attribute(node_string):
    """Extract the file attribute from the node string."""
    match = re.search(r'file=([^\n]+)', node_string)
    if match:
        return match.group(1)  # Return the matched file path
    return None  # Return None if no file attribute is found

def visualize_dependency_graph(dependency_graph):
    dot = graphviz.Digraph(comment='Dependency Graph', graph_attr={'rankdir': 'LR'})
    graph_data = {'nodes': [], 'edges': []}

    for caller, callees in dependency_graph.items():
        caller_file = extract_file_attribute(caller)
        caller_color = hash_string_to_rgb(caller_file if caller_file else caller)
        if caller not in graph_data['nodes']:
            graph_data['nodes'].append(caller)
        dot.node(caller, color=caller_color, style='filled', fillcolor=caller_color)

        for callee in callees:
            callee_file = extract_file_attribute(callee)
            callee_color = hash_string_to_rgb(callee_file if callee_file else callee)
            if callee not in graph_data['nodes']:
                graph_data['nodes'].append(callee)
            graph_data['edges'].append({'source': caller, 'target': callee})

            dot.node(callee, color=callee_color, style='filled', fillcolor=callee_color)
            dot.edge(caller, callee)

    # Save the graph visualization
    dot.render('dependency_graph', view=True)

    # Export the graph data to JSON for further analysis
    with open('dependency_graph.json', 'w') as f:
        json.dump(graph_data, f, indent=4)

def parse_viztracer_output(file_path):
    """
    Parse the VizTracer output from the given file path.
    """
    data = load_json_data(file_path)
    dependency_graph = process_events(data)
    visualize_dependency_graph(dependency_graph)  # Visualize the graph after processing

def main():
    parser = argparse.ArgumentParser(description="Parse VizTracer output JSON file and print call stacks.")
    parser.add_argument('file_path', type=str, help="Path to the VizTracer output JSON file")
    args = parser.parse_args()

    parse_viztracer_output(args.file_path)

if __name__ == "__main__":
    main()
