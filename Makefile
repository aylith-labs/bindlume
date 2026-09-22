PYTHON ?= /usr/bin/python
ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: install uninstall test
install:
	$(PYTHON) "$(ROOT)install.py" install

uninstall:
	$(PYTHON) "$(ROOT)install.py" uninstall

test:
	cd "$(ROOT)" && $(PYTHON) tests/run.py
	cd "$(ROOT)" && QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/qml
