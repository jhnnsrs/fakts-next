import os
from fakts_next.grants.remote.models import FaktsEndpoint
from fakts_next.grants.remote.base import RemoteGrant
from fakts_next.fakts import Fakts
from fakts_next.grants.io.qt.yaml import QtYamlGrant, WrappingWidget, QtSelectYaml
from fakts_next.grants.remote.discovery.qt.selectable_beacon import (
    SelectBeaconWidget,
    QtSelectableDiscovery,
)
from fakts_next.grants.remote.demanders.static import StaticDemander
from fakts_next.grants.remote.claimers.static import StaticClaimer
import uuid
from koil.qt import async_to_qt
from koil.contrib.pytest_qt import wait_for_qttask
from PyQt5 import QtCore, QtWidgets
import pytest 


TESTS_FOLDER = str(os.path.dirname(os.path.abspath(__file__)))


class FaktualBeacon(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent=parent)

        self.fakts_next = Fakts(
            grant=RemoteGrant(
                discovery=QtSelectableDiscovery(widget=SelectBeaconWidget(parent=self)),
                demander=StaticDemander(token="sionsoinsoien"),
                claimer=StaticClaimer(value={"hello": "world"}),
            ),
        )
        self.fakts_next.enter()

        self.load_fakts_next_task = async_to_qt(self.fakts_next.aget)
        self.load_fakts_next_task.errored.connect(
            lambda x: self.greet_label.setText(repr(x))
        )
        self.load_fakts_next_task.returned.connect(
            lambda x: self.greet_label.setText(repr(x))
        )

        self.button_greet = QtWidgets.QPushButton("Greet")
        self.greet_label = QtWidgets.QLabel("")

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.button_greet)
        layout.addWidget(self.greet_label)

        self.setLayout(layout)

        self.button_greet.clicked.connect(self.greet)

    def greet(self):
        self.load_fakts_next_task.run()
        self.greet_label.setText("Loading...")


class FaktualYaml(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent=parent)

        self.fakts_next = Fakts(
            grant=QtYamlGrant(widget=WrappingWidget(parent=self)),
        )
        self.fakts_next.enter()
        self.load_fakts_next_task = async_to_qt(self.fakts_next.aget)
        self.load_fakts_next_task.errored.connect(
            lambda x: self.greet_label.setText(repr(x))
        )
        self.load_fakts_next_task.returned.connect(
            lambda x: self.greet_label.setText(repr(x))
        )

        self.button_greet = QtWidgets.QPushButton("Greet")
        self.greet_label = QtWidgets.QLabel("")

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.button_greet)
        layout.addWidget(self.greet_label)

        self.setLayout(layout)

        self.button_greet.clicked.connect(self.greet)

    def greet(self):
        self.load_fakts_next_task.run()
        self.greet_label.setText("Loading...")


async def mock_aclaim(self, *args, **kwargs):
    return {
        "hello": "world",
    }


async def mock_ademand(self, *args, **kwargs):
    """Mock ademenad

    Returns a fake token for testing purposes"""
    return uuid.uuid4().hex


@pytest.mark.qt
def test_faktual_yaml(qtbot, monkeypatch): 
    """Tests if just adding koil interferes with normal
    qtpy widgets.

    Args:
        qtbot (_type_): _description_
    """

    monkeypatch.setattr(
        QtSelectYaml,
        "ask",
        classmethod(lambda *args, **kwargs: f"{TESTS_FOLDER}/test.yaml"), # type: ignore
    )

    widget = FaktualYaml()
    qtbot.addWidget(widget)

    with qtbot.waitSignal(widget.load_fakts_next_task.returned) as b:
        # click in the Greet button and make sure it updates the appropriate label
        qtbot.mouseClick(widget.button_greet, QtCore.Qt.LeftButton)

        assert widget.greet_label.text() == "Loading..."

    assert isinstance(b.args[0], dict), "Needs to be dict"
