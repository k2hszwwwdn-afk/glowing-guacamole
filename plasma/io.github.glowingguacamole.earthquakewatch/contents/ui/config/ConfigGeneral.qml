import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    id: configPage

    property alias cfg_language: language.currentValue
    property string cfg_languageDefault: "en"

    ColumnLayout {
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 10

        QQC2.Label {
            text: i18n("Choose the language used by the EarthWatch widget.")
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        QQC2.ComboBox {
            id: language
            Layout.fillWidth: true
            textRole: "label"
            valueRole: "value"
            model: [
                { "label": "English", "value": "en" },
                { "label": "中文", "value": "zh" },
                { "label": "Español", "value": "es" },
                { "label": "العربية", "value": "ar" }
            ]
        }
    }
}
