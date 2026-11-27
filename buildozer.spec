[app]
title = SiteManager
package.name = sitemanager
package.domain = org.osihov
package.icon_filename = icon.png
source.dir = .
source.include_exts = py
version = 1.0
requirements = python3,kivy==2.3.0,sqlite3,libffi,openssl
orientation = landscape
fullscreen = 0
android.api = 34
android.minapi = 24
android.ndk = 26b
android.archs = arm64-v8a
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
