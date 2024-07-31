setup:
	python3 -m venv venv
	./venv/bin/pip3 install -r ./requirements.txt

install:
	./venv/bin/pyinstaller ./bqckup.py --onefile --add-data 'templates:templates' --add-data 'static:static'	

clean:
	rm -rf ./venv/ ./dist/ ./build/ *.spec

