.PHONY: backup verify list restore commit help

ARCHIVE ?=
FILENAME ?=
MESSAGE ?= Add encrypted vault backup

VERIFY_ARGS :=
RESTORE_ARGS :=

ifneq ($(strip $(ARCHIVE)),)
VERIFY_ARGS += $(ARCHIVE)
RESTORE_ARGS += $(ARCHIVE)
endif

ifneq ($(strip $(REPLACE_EXISTING)),)
RESTORE_ARGS += --replace-existing
endif

backup:
	BACKUP_FILENAME="$(FILENAME)" ./scripts/backup.sh

verify:
	./scripts/verify.sh $(VERIFY_ARGS)

list:
	./scripts/list.sh

restore:
	./scripts/restore.sh $(RESTORE_ARGS)

commit:
	git add backups/
	git commit -m "$(MESSAGE)"

help:
	@printf '%s\n' \
		'make backup [FILENAME=name.tar.gz.age] - create an encrypted backup' \
		'make list                            - list completed backups' \
		'make verify [ARCHIVE=path]           - verify newest or selected backup' \
		'make restore [ARCHIVE=path] [REPLACE_EXISTING=1] - restore newest or selected backup' \
		'make commit [MESSAGE="..."]          - git add backups/ and commit'
