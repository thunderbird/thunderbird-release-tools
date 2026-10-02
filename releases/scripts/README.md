# bump.sh

Bumps the specified version number of the branch you are currently on, and
commits the change.

*You can check the current version by calling bump.sh with no arguments*

Usage: `bump.sh major|minor|patch`



# pin.sh

Pins checkout to the latest version of Firefox on the current branch.

*Requires Firefox checkout*

Usage: `pin.sh`



# prep.sh

Switches to a branch and makes sure the working copy is synced to the branch's remote tip.

*If no branch is specified, the current branch is updated instead*

Usage: `prep.sh [branch]`



# uplift.sh

Uplifts the specified changeset to the current checkout with the specified approver.

*Compatible with both git and Mercurial hashes*

Usage: `uplift.sh approver [changeset|--continue]`