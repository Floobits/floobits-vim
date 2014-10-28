import floobits

# code run after our own by other plugins can not pollute the floobits namespace
__globals = globals()
for k, v in floobits.__dict__.items():
    __globals[k] = v

# Vim essentially runs python by concating the python string into a single python file and running it.
# Before we did this, the following would happen:

# 1. import utils
# 2. from ycm import utils
# 3. utils.parse_url # references the wrong utils ...
