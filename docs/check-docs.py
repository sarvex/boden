import os, sys, subprocess

output = subprocess.run([sys.executable, '-m', 'mkdocs', 'build', '-c'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

print(output.stdout.decode("utf-8") )
print(output.stderr.decode("utf-8") )

if output.returncode != 0:
	print("Command exited with error")
	exit(output.returncode)

for line in output.stderr.decode("utf-8").split('\n'):
	if line.startswith("WARNING"):
		print(f"Failed due to: {line}")
		exit(1)
