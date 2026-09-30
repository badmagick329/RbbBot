# Privacy policy

This policy explains what the RBB Discord bot processes, what it stores, and the controls available to you.

Effective 18 July 2026 · Last updated 8 August 2026

## Contents

1. [Scope](#scope)
2. [Data used](#data-used)
3. [Retention](#retention)
4. [Your controls](#your-controls)
5. [Storage](#storage)
6. [Contact](#contact)

<a id="scope"></a>

_01 / Scope_

## What this policy covers

RBB is a Discord bot. This policy covers information processed by the bot when it is used in Discord servers or direct messages. It does not replace Discord's own privacy policy or the policies of individual Discord servers.

<a id="data-used"></a>

_02 / Data used_

## Information RBB uses

### Guild configuration

RBB stores guild and channel IDs, configured prefixes, role IDs, welcome/join settings, logging settings, tags, tag responses, and administrator-configured welcome-response text or URLs. These settings allow each server to configure the bot's features.

### Reminders and source submissions

For reminders, RBB stores the Discord user ID, relevant guild/channel IDs, reminder text, and timing information. For emoji source submissions, it stores the submitting user's Discord ID, a cached username, source metadata, URLs, and relevant Discord message/channel identifiers needed for moderation and attribution.

### Automatic tag responses

RBB checks messages sent in a server against that server's configured tag triggers and may send an automatic response.

### Requested command inputs

When a user explicitly uses a command that accepts text, a URL, or an image attachment, RBB processes that input to provide the requested result. RBB does not store those inputs unless they are saved as a reminder, source submission, or server configuration described above.

### Welcome-message URL imports

When a server administrator asks RBB to import URLs from a selected channel for welcome messages, RBB reads message text and attachment URLs in that channel to extract and store the URLs as welcome-message configuration.

### Optional guild logging

If a server administrator enables message edit or deletion logging, RBB copies the relevant message text, author information, channel, message ID, and timestamps to that server's chosen Discord log channel.

<a id="retention"></a>

_03 / Retention_

## How long information is kept

- **Guild configuration:** kept while RBB is installed. When RBB leaves a configured server, the data is kept for a 7-day re-invite grace period. Re-inviting RBB in that period cancels the deletion; otherwise the guild-scoped configuration is deleted.
- **Reminders:** deleted after successful delivery, manual removal, user deletion, or applicable guild cleanup. A reminder that cannot be delivered can remain pending until it is delivered or removed.
- **Source submissions and user state:** retained while needed for the source-submission and moderation features, unless deleted through the controls below or applicable guild cleanup.
- **Tags and responses:** treated as guild configuration and deleted under the same guild-departure rule.

<a id="your-controls"></a>

_04 / Your controls_

## Access, opt-out, and deletion

RBB provides slash commands under **/privacy** for self-service controls:

- **/privacy export** provides a JSON file containing the data RBB stores about you.
- **/privacy policy** returns a link to this policy.
- **/privacy tags** shows or changes your global automatic tag-response preference.
- **/privacy delete** asks for confirmation, then deletes your reminders, source submissions, cached username, source blacklist state, and tag preference.

> A privacy deletion cannot remove copies previously posted in a server's optional Discord logging channel. Contact that server's administrators to ask about removing those Discord messages.

<a id="storage"></a>

_05 / Storage_

## Where information is stored

RBB stores the information described in this policy in the database used to operate the bot.

Retained Discord, user, and administrator-supplied content is encrypted before it is stored in that database.

<a id="contact"></a>

_06 / Contact_

## Questions or requests

For a privacy question, correction request, or help using the privacy controls, contact **badmagick** on Discord.

Discord user ID: `221379755830804480`

---

RBB Privacy Policy · Effective 18 July 2026 · Last updated 8 August 2026
