# Anki Voice Field

`helper_project_folder`
: The folder containing the helper. Use `__BUNDLED__` to use the helper folder
  packaged inside the add-on.

`helper_pythonw_path`
: The Python executable used to start the helper without opening a console. Use
  `__AUTO__` to use the bundled helper's `.venv`.

`control_url`
: The local helper control server URL.

`auto_start_helper`
: When true, the add-on starts the helper if it is not already running.

`auto_launch_helper_on_anki_startup`
: When true, Anki quietly starts the helper at launch if the helper environment
  already exists.

`auto_setup_helper`
: When true, the add-on may launch the first-time PowerShell setup script if the
  helper environment is missing. The default is false so Anki startup never
  opens a setup window or downloads packages unexpectedly.

`show_advanced_menu_items`
: When false, the Tools menu only shows `Anki Voice Field: Record / Stop`.
  When true, extra test/debug helper actions are shown.

`target_field_name`
: The preferred field to append notes into.

`image_occlusion_model_hints`
: If the note type name contains one of these strings, the add-on treats it as
  an Image Occlusion note.

`image_occlusion_fallback_field_name`
: The field used for Image Occlusion notes when `target_field_name` is missing.

`default_fallback_field_names`
: Fields tried when neither `target_field_name` nor the Image Occlusion fallback
  applies.

`hotkey`
: The Anki-local shortcut for toggling recording through the helper.
