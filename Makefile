.PHONY: backup verify list restore help

backup:
	./scripts/backup.sh

verify:
	./scripts/verify.sh

list:
	./scripts/list.sh

restore:
	./scripts/restore.sh

help:
	@printf '%s\n' \
		'make backup   - run ./scripts/backup.sh' \
		'make verify   - run ./scripts/verify.sh' \
		'make list     - run ./scripts/list.sh' \
		'make restore  - run ./scripts/restore.sh'
