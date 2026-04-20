import sys
lines = open('audit_output.log', errors='ignore').readlines()
for i, line in enumerate(lines):
    if 'FAILURE' in line or 'Exception' in line or 'Traceback' in line or 'Original:' in line or 'Duplicate attempt:' in line:
        print(line.strip())
