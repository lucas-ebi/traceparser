import json
import argparse
from collections import defaultdict
import graphviz
import hashlib

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
    # Splitting the input string to extract the relevant parts
    function_name, file_path_with_line = input_str.split(" (")
    # Check if the function name has no "<" or ">" characters
    if "<" not in function_name and ">" not in function_name:
        file_path = file_path_with_line.split(":")[0]  # Removing line number

        # Normalizing the file path
        base_path = "/nfs/production/gerard/pdbe/onedep/deployments/emdb_dev_1/source/"
        normalized_path = file_path.replace(base_path, "").replace(".py", "")

        # Converting path separators to dots for module notation
        module_notation = normalized_path.replace("/", ".")

        # Splitting the string at ".wwpdb" and taking the part after it
        parts = module_notation.split(".wwpdb", 1)  # The '1' limits the split to only the first occurrence
        if len(parts) > 1:
            module_notation = "wwpdb" + parts[1]  # Prepend ".wwpdb" since it's removed by split

        if module_notation == "wwpdb.apps.deposit.depui.upload":
            # Add file_upload_submit to the module notation
            module_notation += ".file_upload_submit"

        # Concatenating to get the desired format
        formatted_str = f"{module_notation}.{function_name}"
        
        return formatted_str

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
                caller = format_function_call(event_stack[-1]['name'])
                callee = format_function_call(popped_event['name'])
                if caller and callee:
                    dependency_graph[caller].add(callee)

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
        formatted_str = format_function_call(input_str)  # Assuming this function exists and formats the string
        if formatted_str:
            print(f"{indent}{branch_symbol}{formatted_str}")

        event['end'] = event_end
        event_stack.append(event)
    
    return dependency_graph  # Return the graph for visualization

def visualize_dependency_graph(dependency_graph):
    dot = graphviz.Digraph(comment='Dependency Graph', graph_attr={'rankdir': 'LR'})
    graph_data = {'nodes': [], 'edges': []}  # Initialize the structure for JSON export

    for caller, callees in dependency_graph.items():
        caller_color = hash_string_to_rgb(caller)
        if caller not in graph_data['nodes']:
            graph_data['nodes'].append(caller)
        dot.node(caller, color=caller_color, style='filled', fillcolor=caller_color)

        for callee in callees:
            callee_color = hash_string_to_rgb(callee)
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
