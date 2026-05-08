Bolt 2.0

Garde Cavalry utility bot. Made by orbandit, maintained by orbandit (@just_whiz on Discord).

/accept — Approves a pending join request in the Roblox group and sets them to Citoyen. Takes one or more @mentions. Has a dropdown to choose which group (Empire Français or Cavalry Corps — stubbed for now since we're testing with Bandits Hideout).

/background-check — Looks up a Discord user via Bloxlink, pulls their Roblox account age, current rank in both groups, and previous usernames via the Roblox API. Coalition/Clients & France fields are left as placeholders.

/induct — Checks the user is in the group and is at least Citoyen, runs a background check gate, assigns Discord roles (company + rank), sets Roblox rank to Conscrit, updates nickname, removes Garde Nationale role, and posts the formatted results embed.

/draft — Takes one or more @mentions, strips current company/rank roles, assigns new company roles, resets Roblox rank back to Conscrit, updates nickname.
Local JSON cache — Stored in verified_users.json, maps Discord ID → Roblox ID + username. Checked before calling Bloxlink to avoid unnecessary API calls.