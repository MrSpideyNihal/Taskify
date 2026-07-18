# Taskify Makefile target shortcuts

.PHONY: dist clean test lint typecheck

dist:
	python packaging/build.py

clean:
	python -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ('build', 'dist')]"

test:
	pytest tests/unit/ -v

lint:
	ruff check src/ --fix

typecheck:
	mypy src/
