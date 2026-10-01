Changes:


content/services/plex.py	
Changed Plex watchlist API host from metadata.provider.plex.tv → discover.provider.plex.tv	
Plex's old metadata endpoint was failing/unreachable for watchlist operations

settings/__init__.py	
Changed the Plex user/watchlist validation endpoint to discover.provider.plex.tv	Keeps Plex setup/validation consistent with the new working endpoint

releases/__init__.py	
Improved magnet BTIH hash extraction	
Some valid magnets weren't producing a release.hash, so Debrid-Link couldn't process them

scraper/services/prowlarr.py	
Reworked Prowlarr magnet/torrent resolution	
Prowlarr results weren't reliably yielding usable magnet links/hashes

debrid/services/debridlink.py	
Reworked Debrid-Link cache/download handling around the current API behavior	
Debrid-Link disabled the old /seedbox/cached endpoint, which broke plex_debrid's original cache-check workflow
