import re
str = "/commen/sjc/abc"
print(re.findall(r".*/(.*)", str))
print(re.findall(r"(.*/).*", str))