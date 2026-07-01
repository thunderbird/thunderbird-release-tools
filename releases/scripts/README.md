# bump.sh

Bumps the specified version number of the branch you are currently on, and
commits the change.

`bump.sh major|minor|patch`



# pin.sh

Pins checkout to the latest version of Firefox on the current branch.

*Requires Firefox checkout*

`pin.sh`



# uplift.sh

Uplifts the specified changeset to the current checkout with the specified approver.

*Currently only supports git hashes*

`uplift.sh approver changeset`