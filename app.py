import sys

from goldmonitor import application


if __name__ == "__main__":
    application.main()
else:
    sys.modules[__name__] = application
