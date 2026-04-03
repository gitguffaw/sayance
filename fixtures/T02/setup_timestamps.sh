#!/bin/sh
# Set old timestamps on 2 files, ensure new_web.conf is fresh.
# Run this in the fixture's working directory after copying.
touch conf/new_web.conf                                # mtime = now (always < 1 day old)
touch -t 202501010000 conf/old_app.conf conf/old_db.conf  # mtime = Jan 2025 (always > 1 day old)
