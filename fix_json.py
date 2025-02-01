import json
import re
import sys
import argparse

def fix_json_file(input_filename, output_filename):
    # Read the entire file content
    with open(input_filename, 'r', encoding='utf-8') as f:
        data = f.read().strip()

    # Insert commas between JSON objects.
    # This assumes that each top-level object ends with '}' and the next one starts with '{'
    # (even if there are newlines or spaces between).
    fixed_data = re.sub(r'}\s*{', '},\n{', data)

    # Wrap the entire string in [ ... ] to form a JSON array.
    fixed_data = f'[{fixed_data}]'

    # Test if the new JSON is valid.
    try:
        json_objects = json.loads(fixed_data)
    except json.JSONDecodeError as e:
        print("Error decoding JSON:", e)
        sys.exit(1)

    # Write out the fixed JSON with pretty formatting.
    with open(output_filename, 'w', encoding='utf-8') as out_file:
        json.dump(json_objects, out_file, indent=4, ensure_ascii=False)

    print(f"Fixed JSON file has been written to: {output_filename}")

def main():
    parser = argparse.ArgumentParser(description="Fix a JSON file with multiple top-level objects by wrapping them in an array.")
    parser.add_argument("input", help="Path to the input JSON file")
    parser.add_argument("output", help="Path to the output fixed JSON file")
    args = parser.parse_args()

    fix_json_file(args.input, args.output)

if __name__ == '__main__':
    main()
