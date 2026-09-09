CC = gcc
CFLAGS = -O0 -g -std=c11 -Wall -Wextra -Werror -fno-omit-frame-pointer
.PHONY: all test clean
all: build/cache_bench build/cache_bench.s build/cache_bench.dis build/page_control build/followup_bench
build:
	mkdir -p build
build/cache_bench: src/cache_bench.c | build
	$(CC) $(CFLAGS) $< -o $@
build/cache_bench.s: src/cache_bench.c | build
	$(CC) $(CFLAGS) -S $< -o $@
build/cache_bench.dis: build/cache_bench
	objdump -d $< > $@
build/page_control: src/page_control.c src/cache_bench.c | build
	$(CC) $(CFLAGS) $< -o $@
build/followup_bench: src/followup_bench.c src/cache_bench.c | build
	$(CC) $(CFLAGS) -pthread $< -o $@
test: all
	python3 -m py_compile scripts/*.py
	python3 -m unittest discover -s tests -v
clean:
	rm -rf build
