# Test methods with long descriptive names can omit docstrings
# pylint: disable=all

import gc
import weakref

from unittest.mock import patch, MagicMock

from AnyQt.QtCore import QRect, QByteArray, QObject, pyqtSignal
from AnyQt.QtGui import QShowEvent
from AnyQt.QtWidgets import QAction
from AnyQt.QtTest import QSignalSpy

from Orange.widgets.gui import OWComponent
from Orange.widgets.settings import Setting
from Orange.widgets.tests.base import WidgetTest
from Orange.widgets.widget import OWWidget, Msg


class DummyComponent(OWComponent):
    b = None


class MyWidget(OWWidget):
    name = "Dummy"

    field = Setting(42)

    def __init__(self):
        super().__init__()

        self.component = DummyComponent(self)
        self.widget = None


class WidgetTestCase(WidgetTest):
    def test_setattr(self):
        widget = self.create_widget(MyWidget)
        widget.widget = self.create_widget(MyWidget)

        setattr(widget, 'field', 1)
        self.assertEqual(widget.field, 1)

        setattr(widget, 'component.b', 2)
        self.assertEqual(widget.component.b, 2)

        setattr(widget, 'widget.field', 3)
        self.assertEqual(widget.widget.field, 3)

        setattr(widget, 'unknown_field', 4)
        self.assertEqual(widget.unknown_field, 4)

        with self.assertRaises(AttributeError):
            setattr(widget, 'widget.widget.field', 5)

        with self.assertRaises(AttributeError):
            setattr(widget, 'unknown_field2.field', 6)

    def test_notify_controller_on_attribute_change(self):
        widget = self.create_widget(MyWidget)

        callback = MagicMock()
        callback2 = MagicMock()

        widget.connect_control('field', callback)
        widget.connect_control('field', callback2)
        widget.field = 5
        self.assertTrue(callback.called)
        self.assertTrue(callback2.called)

    def test_widget_tests_do_not_use_stored_settings(self):
        widget = self.create_widget(MyWidget)

        widget.field = 5
        widget.saveSettings()

        widget2 = self.create_widget(MyWidget)
        self.assertEqual(widget2.field, 42)

    def test_widget_help_action(self):
        widget = self.create_widget(MyWidget)
        help_action = widget.findChild(QAction, "action-help")
        help_action.setEnabled(True)
        help_action.setVisible(True)

    def test_widget_without_basic_layout(self):
        class TestWidget2(OWWidget):
            name = "Test"

            want_basic_layout = False

        w = TestWidget2()
        w.showEvent(QShowEvent())


class WidgetMsgTestCase(WidgetTest):

    class TestWidget(OWWidget):
        name = "Test"

        class Information(OWWidget.Information):
            hello = Msg("A message")

        def __init__(self):
            super().__init__()

            self.Information.hello()

    @staticmethod
    def active_messages(widget):
        """Return all active messages in a widget"""
        return [m for g in widget.message_groups for m in g.active]

    def test_widget_emits_messages(self):
        """Widget emits messageActivates/messageDeactivated signals"""

        w = WidgetMsgTestCase.TestWidget()
        messages = set(self.active_messages(w))

        self.assertEqual(len(messages), 1, )

        w.messageActivated.connect(messages.add)
        w.messageDeactivated.connect(messages.remove)

        w.Information.hello()
        self.assertEqual(len(messages), 1)
        self.assertSetEqual(messages, set(self.active_messages(w)))

        w.Information.hello.clear()
        self.assertEqual(len(messages), 0)
        self.assertSetEqual(set(self.active_messages(w)), set())

        with patch.object(
                WidgetMsgTestCase.TestWidget,
                "want_basic_layout", False):
            # OWWidget without a basic layout (completely empty; no default
            # message bar)
            w = WidgetMsgTestCase.TestWidget()

        messages = set(self.active_messages(w))

        w.messageActivated.connect(messages.add)
        w.messageDeactivated.connect(messages.remove)

        self.assertEqual(len(messages), 1)

        w.Information.hello.clear()
        self.assertEqual(len(messages), 0)

    def test_message_exc_info(self):
        w = WidgetMsgTestCase.TestWidget()
        w.Error.add_message("error")
        messages = set([])
        w.messageActivated.connect(messages.add)
        w.messageDeactivated.connect(messages.remove)
        try:
            _ = 1 / 0
        except ZeroDivisionError:
            w.Error.error("AA", exc_info=True)

        self.assertEqual(len(messages), 1)
        m = list(messages).pop()
        self.assertIsNotNone(m.tb)
        self.assertIn("ZeroDivisionError", m.tb)

        w.Error.error("BB", exc_info=Exception("foobar"))
        self.assertIn("foobar", m.tb)
        w.Error.error("BB")
        self.assertIsNone(m.tb)

    def test_old_style_messages(self):
        w = WidgetMsgTestCase.TestWidget()
        w.Information.clear()

        messages = set(self.active_messages(w))

        w.messageActivated.connect(messages.add)
        w.messageDeactivated.connect(messages.remove)

        w.error(1, "A")

        self.assertEqual(len(w.Error.active), 1)
        self.assertEqual(len(messages), 1)

        w.error(1)

        self.assertEqual(len(messages), 0)
        self.assertEqual(len(w.Error.active), 0)

        w.error(2, "B")
        self.assertEqual(len(messages), 1)

        w.Error.clear()
        self.assertEqual(len(messages), 0)

    def test_store_restore_layout_geom(self):
        class Widget(OWWidget):
            name = "Who"
            want_control_area = True

        w = Widget()
        w._OWWidget__setControlAreaVisible(False)
        w.setGeometry(QRect(51, 52, 53, 54))
        state = w.saveGeometryAndLayoutState()
        w1 = Widget()
        self.assertTrue(w1.restoreGeometryAndLayoutState(state))
        self.assertEqual(w1.geometry(), QRect(51, 52, 53, 54))
        self.assertFalse(w1.controlAreaVisible)

        Widget.want_control_area = False
        w2 = Widget()
        self.assertTrue(w2.restoreGeometryAndLayoutState(state))
        self.assertEqual(w1.geometry(), QRect(51, 52, 53, 54))

        self.assertFalse((w2.restoreGeometryAndLayoutState(QByteArray())))
        self.assertFalse(w2.restoreGeometryAndLayoutState(QByteArray(b'ab')))

    def test_garbage_collect(self):
        widget = MyWidget()
        ref = weakref.ref(widget)
        # insert an object in widget's __dict__ that will be deleted when its
        # __dict__ is cleared.
        widget._finalizer = QObject()
        spyw = DestroyedSignalSpy(widget)
        spyf = DestroyedSignalSpy(widget._finalizer)
        widget.deleteLater()
        del widget
        gc.collect()
        self.assertTrue(len(spyw) == 1 or spyw.wait(1000))
        gc.collect()
        self.assertTrue(len(spyf) == 1 or spyf.wait(1000))
        gc.collect()
        self.assertIsNone(ref())

    def test_garbage_collect_from_scheme(self):
        from Orange.canvas.scheme.widgetsscheme import WidgetsScheme
        from Orange.canvas.registry.description import WidgetDescription
        new_scheme = WidgetsScheme()
        w_desc = WidgetDescription.from_module("Orange.widgets.tests.test_widget")
        node = new_scheme.new_node(w_desc)
        widget = new_scheme.widget_for_node(node)
        widget._finalizer = QObject()
        spyw = DestroyedSignalSpy(widget)
        spyf = DestroyedSignalSpy(widget._finalizer)
        ref = weakref.ref(widget)
        del widget
        new_scheme.remove_node(node)
        gc.collect()
        self.assertTrue(len(spyw) == 1 or spyw.wait(1000))
        gc.collect()
        self.assertTrue(len(spyf) == 1 or spyf.wait(1000))
        self.assertIsNone(ref())


class DestroyedSignalSpy(QSignalSpy):
    """
    A signal spy for watching QObject.destroyed signal

    NOTE: This class specifically does not capture the QObject pointer emitted
    from the destroyed signal (i.e. it connects to the no arg overload).
    """
    class Mapper(QObject):
        destroyed_ = pyqtSignal()

    def __init__(self, obj):
        # type: (QObject) -> None
        # Route the signal via a no argument signal to drop the obj pointer.
        # After the destroyed signal is emitted the pointer is invalid
        self.__mapper = DestroyedSignalSpy.Mapper()
        obj.destroyed.connect(self.__mapper.destroyed_)
        super().__init__(self.__mapper.destroyed_)
