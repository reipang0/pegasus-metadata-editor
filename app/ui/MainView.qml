import QtQuick 2.15
import QtQuick.Controls 2.15

ApplicationWindow {
  visible: true
  width: 1200; height: 800
  title: "Pegasus Metadata Editor"
  Column {
    anchors.centerIn: parent
    spacing: 12
    Text { text: "Hello Pegasus"; font.pointSize: 20 }
    Button { text: "수동 매핑 (Manual Mapping)" }
  }
}
