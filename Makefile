
all:
	epydoc --parse-only honeyclient/ -o docs -v

clean_docs:
	rm -Rf docs