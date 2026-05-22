# Umbrel app folder

These files are a mirror of what lives in the community app store repo at:

`lunaticoin-umbrel-app-store/lunaticoin-umbrelanalyser/`

After bumping `version` here, copy the same `docker-compose.yml` + `umbrel-app.yml`
(with the new pinned digest) into the store repo, commit and push both.

## Required: icon

You must add `icon.png` (512×512) to **this folder** AND to the store-repo folder
before the app will install cleanly. It is not in git on purpose — drop your own.
