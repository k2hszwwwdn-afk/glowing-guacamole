import QtQuick
import org.kde.plasma.configuration

ConfigModel {
    ConfigCategory {
        name: i18n("Language")
        icon: "preferences-desktop-locale"
        source: "config/ConfigGeneral.qml"
    }
}
