# bump.sh

Bumps the specified version number of the branch you are currently on, and
commits the change.

*You can check the current version by calling bump.sh with no arguments*

Usage: `bump.sh [--help/-h] [major|minor|patch]`


# land.sh

Lands local patches to remote Thunderbird branch, then updates local repo with remote changes.

*For safety, remote branch must always be specified*

Usage: `land.sh [--help/-h] branch`


# pin.sh

Pins checkout to the latest version of Firefox on the current branch.

Pass -t to pin to tip instead.

*Requires Firefox checkout*

Usage: `pin.sh [--help/-h|--tip/-t]`


# prep.sh

Switches to a branch and makes sure the working copy is synced to the branch's remote tip.

If no branch is specified, the current branch is updated instead.

Usage: `prep.sh [--help/-h] branch`


# uplift.sh

Uplifts a git or mercurial changeset to the current checkout and adds the approver to the commit message.

Pass -p to use Phabricator ID instead of changeset.

Usage: `uplift.sh [--help/-h|--phab/-p|--continue/-c] approver [changeset|phab ID]`


# changes-since-pin.sh

Lists the Firefox changes that landed on the pinned branch after the revision in
`.gecko_rev.yml`, so the release engineer can decide whether another build is needed
(e.g. a new beta after pinning the final beta to tip).

*Requires Firefox checkout, `curl` and `jq`*

Usage: `changes-since-pin.sh`

