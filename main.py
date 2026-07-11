"""DEDisplay — оверлей для рисования поверх экрана. Точка входа."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from overlay import keymap, style_prefs
from overlay.canvas import OverlayCanvas
from overlay.hotkeys import HotkeyManager
from overlay.page_switcher import PageSwitcher
from overlay.settings_dialog import SettingsDialog
from overlay.strokes import PageManager
from overlay.toolbar import Toolbar
from overlay.tray import TrayIcon


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    page_manager = PageManager()
    canvas = OverlayCanvas(page_manager)
    toolbar = Toolbar()
    page_switcher = PageSwitcher()
    tray = TrayIcon()
    hotkeys = HotkeyManager()

    def sync_pages() -> None:
        page_switcher.set_pages(page_manager.count, page_manager.current_index)

    def go_to_page(index: int) -> None:
        canvas.set_page(index)
        sync_pages()

    def add_page() -> None:
        idx = page_manager.add_page()
        go_to_page(idx)

    def toggle_ui() -> None:
        visible = not toolbar.isVisible()
        toolbar.setVisible(visible)
        page_switcher.setVisible(visible)

    hidden_all = False

    def toggle_hide_all() -> None:
        nonlocal hidden_all
        hidden_all = not hidden_all
        if hidden_all:
            if canvas.draw_mode:
                canvas.set_draw_mode(False)
            canvas.hide()
            toolbar.hide()
            page_switcher.hide()
            # снимаем регистрацию остальных глобальных хоткеев на уровне ОС,
            # иначе RegisterHotKey продолжает эксклюзивно перехватывать их
            # комбинации (например Ctrl+Space) и они не доходят до других
            # приложений, даже если сам обработчик их игнорирует
            for name in keymap.get_global_bindings():
                if name != keymap.HIDE_ALL:
                    hotkeys.unregister(name)
        else:
            for name, (mod, vk) in keymap.get_global_bindings().items():
                if name != keymap.HIDE_ALL:
                    hotkeys.register_one(name, mod, vk)
            canvas.show()
            toolbar.show()
            page_switcher.show()

    # --- тулбар -> канвас ---
    toolbar.tool_selected.connect(canvas.set_tool)
    toolbar.color_selected.connect(canvas.set_color)
    toolbar.brush_width_changed.connect(canvas.set_brush_width)
    toolbar.undo_requested.connect(canvas.undo)
    toolbar.redo_requested.connect(canvas.redo)
    toolbar.copy_requested.connect(canvas.copy_selection)
    toolbar.paste_requested.connect(canvas.paste_clipboard)
    toolbar.clear_page_requested.connect(canvas.clear_page)
    toolbar.toggle_draw_mode_requested.connect(canvas.toggle_draw_mode)
    toolbar.add_page_requested.connect(add_page)

    # --- канвас -> тулбар/трей (обратная синхронизация состояния) ---
    canvas.tool_changed.connect(toolbar.set_tool)
    canvas.color_changed.connect(toolbar.set_color)
    canvas.draw_mode_changed.connect(toolbar.set_draw_mode)
    canvas.draw_mode_changed.connect(tray.set_draw_mode)
    canvas.history_changed.connect(toolbar.set_history_state)
    canvas.selection_changed.connect(toolbar.set_copy_enabled)
    canvas.clipboard_changed.connect(toolbar.set_paste_enabled)

    # --- переключатель страниц ---
    page_switcher.page_selected.connect(go_to_page)
    page_switcher.add_page_requested.connect(add_page)

    # --- трей ---
    tray.toggle_draw_mode_requested.connect(canvas.toggle_draw_mode)
    tray.toggle_ui_requested.connect(toggle_ui)
    tray.quit_requested.connect(app.quit)

    # --- выбор стиля оформления ---
    def apply_style(style: str) -> None:
        toolbar.set_style(style)
        page_switcher.set_style(style)
        tray.set_style(style)

    def on_style_selected(style: str) -> None:
        apply_style(style)
        style_prefs.save_style(style)

    tray.style_selected.connect(on_style_selected)
    apply_style(style_prefs.load_style())

    # --- глобальные хоткеи ---
    def on_hotkey(name: str) -> None:
        if hidden_all and name != keymap.HIDE_ALL:
            return
        if name == keymap.TOGGLE_DRAW:
            canvas.toggle_draw_mode()
        elif name == keymap.TOGGLE_UI or name == keymap.TOGGLE_UI_SPACE:
            toggle_ui()
        elif name == keymap.HIDE_ALL:
            toggle_hide_all()
        elif name == keymap.QUIT:
            app.quit()
        elif name == keymap.PREV_PAGE:
            go_to_page(page_manager.prev_page())
        elif name == keymap.NEXT_PAGE:
            go_to_page(page_manager.next_page())
        elif name.startswith(keymap.PAGE_PREFIX):
            page_num = int(name[len(keymap.PAGE_PREFIX):])
            index = page_num - 1
            if index < page_manager.count:
                go_to_page(index)

    hotkeys.hotkey_triggered.connect(on_hotkey)
    app.installNativeEventFilter(hotkeys)
    failed = hotkeys.register_all(keymap.get_global_bindings())
    if failed:
        print(f"Не удалось зарегистрировать хоткеи (заняты другой программой): {failed}", file=sys.stderr)
    app.aboutToQuit.connect(hotkeys.unregister_all)

    # --- настройки биндов ---
    settings_dialog = SettingsDialog(canvas, hotkeys)
    tray.settings_requested.connect(settings_dialog.open_and_raise)

    # начальная синхронизация UI с состоянием
    toolbar.set_history_state(page_manager.current_page.can_undo, page_manager.current_page.can_redo)
    sync_pages()

    canvas.show()
    toolbar.show()
    page_switcher.show()
    tray.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
