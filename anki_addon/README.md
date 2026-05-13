# Anki Voice Field Add-on

This is Phase 2 of `anki_voice_field`.

The current add-on is a personal-use controller for the working Phase 1 helper.
It runs inside Anki, owns the Anki-local hotkey/menu actions, and sends commands
to the external helper over localhost.

## What It Proves

- The add-on loads inside Anki.
- It can add a Tools menu item.
- It can register a hotkey inside Anki.
- It can start/show the external helper.
- It can send the toggle-recording command to the helper.
- It can bind `F8` inside Anki.
- It still includes a typed-note debug action for testing native note edits.

## Install For Local Testing

1. Open Anki.
2. Go to `Tools > Add-ons`.
3. Click `View Files`.
4. Copy this folder into the `addons21` folder:

```text
anki_addon/anki_voice_field
```

5. Restart Anki.
6. Start reviewing a card.
7. Use `Tools > Anki Voice Field: Record / Stop`.

The default hotkey is `F8`. When the add-on starts the helper, it starts it with
the helper's global hotkey disabled, so Anki owns `F8`.

## Next Step

The default menu is intentionally simple. Extra test/debug actions can be shown
by setting `show_advanced_menu_items` to `true` in the add-on config.
