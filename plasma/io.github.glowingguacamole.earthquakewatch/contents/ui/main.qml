import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.plasma.plasmoid

PlasmoidItem {
    id: root

    readonly property string feedUrl: "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
    property var events: []
    property var strongest: null
    property string errorMessage: ""
    property bool loading: true
    property var generatedAt: null
    property var activeRequest: null
    property string language: Plasmoid.configuration.language || "en"

    Plasmoid.title: root.tr("appTitle")
    Plasmoid.icon: "earthwatch"
    preferredRepresentation: fullRepresentation

    function tr(key) {
        var catalog = {
            en: {
                appTitle: "EarthWatch", loading: "EarthWatch…", live: "● LIVE", offline: "OFFLINE",
                headline: "GLOBAL SEISMIC ACTIVITY", pastDay: "PAST 24 HOURS",
                reported: "reported earthquakes", strongest: "STRONGEST", awaiting: "Awaiting events",
                latest: "LATEST EVENTS", refresh: "Refresh now", unknown: "Unknown location",
                unavailable: "USGS feed unavailable", unexpected: "Unexpected feed response",
                readError: "Could not read the USGS feed", timeout: "USGS request timed out",
                noEvents: "No events in this feed", source: "USGS Earthquake Hazards Program",
                depth: "deep", feed: "USGS feed"
            },
            zh: {
                appTitle: "地震观察", loading: "地震观察…", live: "● 实时", offline: "离线",
                headline: "全球地震活动", pastDay: "过去 24 小时",
                reported: "次地震", strongest: "最强地震", awaiting: "等待地震事件",
                latest: "最新事件", refresh: "立即刷新", unknown: "位置未知",
                unavailable: "USGS 数据源不可用", unexpected: "数据源响应格式异常",
                readError: "无法读取 USGS 数据", timeout: "USGS 请求超时",
                noEvents: "此数据源中没有事件", source: "USGS 地震灾害计划",
                depth: "深", feed: "USGS 数据"
            },
            es: {
                appTitle: "EarthWatch", loading: "EarthWatch…", live: "● EN VIVO", offline: "SIN CONEXIÓN",
                headline: "ACTIVIDAD SÍSMICA GLOBAL", pastDay: "ÚLTIMAS 24 HORAS",
                reported: "terremotos registrados", strongest: "MÁS FUERTE", awaiting: "Esperando eventos",
                latest: "EVENTOS RECIENTES", refresh: "Actualizar ahora", unknown: "Ubicación desconocida",
                unavailable: "Fuente de USGS no disponible", unexpected: "Respuesta inesperada",
                readError: "No se pudo leer la fuente de USGS", timeout: "Tiempo de espera agotado",
                noEvents: "No hay eventos en esta fuente", source: "Programa de riesgos sísmicos de USGS",
                depth: "de profundidad", feed: "Fuente USGS"
            },
            ar: {
                appTitle: "مراقب الزلازل", loading: "جارٍ التحميل…", live: "● مباشر", offline: "غير متصل",
                headline: "النشاط الزلزالي العالمي", pastDay: "آخر 24 ساعة",
                reported: "زلازل مسجلة", strongest: "الأقوى", awaiting: "بانتظار الأحداث",
                latest: "أحدث الأحداث", refresh: "تحديث الآن", unknown: "موقع غير معروف",
                unavailable: "مصدر USGS غير متاح", unexpected: "استجابة غير متوقعة",
                readError: "تعذرت قراءة بيانات USGS", timeout: "انتهت مهلة طلب USGS",
                noEvents: "لا توجد أحداث في هذا المصدر", source: "برنامج USGS لمخاطر الزلازل",
                depth: "عمق", feed: "بيانات USGS"
            }
        }
        var selectedCatalog = catalog[root.language] || catalog.en
        return selectedCatalog[key] || catalog.en[key] || key
    }

    function eventCountText() {
        if (language === "zh")
            return events.length.toLocaleString() + " 个事件"
        if (language === "es")
            return events.length.toLocaleString() + " eventos"
        if (language === "ar")
            return events.length.toLocaleString() + " أحداث"
        return events.length.toLocaleString() + " events"
    }

    function refreshFeed() {
        if (activeRequest && activeRequest.readyState !== XMLHttpRequest.DONE)
            return
        var request = new XMLHttpRequest()
        activeRequest = request
        request.open("GET", feedUrl)
        request.timeout = 15000
        request.setRequestHeader("Accept", "application/geo+json, application/json")
        request.setRequestHeader("Cache-Control", "no-cache")
        request.onreadystatechange = function() {
            if (request.readyState !== XMLHttpRequest.DONE)
                return
            if (activeRequest !== request)
                return
            activeRequest = null
            loading = false
            if (request.status < 200 || request.status >= 300) {
                errorMessage = tr("unavailable")
                return
            }
            try {
                var response = JSON.parse(request.responseText)
                if (!response || response.type !== "FeatureCollection"
                        || !Array.isArray(response.features)) {
                    errorMessage = tr("unexpected")
                    return
                }
                var validEvents = []
                response.features.forEach(function(feature) {
                    if (!feature || !feature.properties || !feature.geometry
                            || feature.geometry.type !== "Point"
                            || !Array.isArray(feature.geometry.coordinates)
                            || feature.geometry.coordinates.length < 3) {
                        return
                    }
                    var coordinates = feature.geometry.coordinates
                    var properties = feature.properties
                    if (typeof properties.time !== "number"
                            || typeof coordinates[0] !== "number"
                            || typeof coordinates[1] !== "number"
                            || typeof coordinates[2] !== "number") {
                        return
                    }
                    validEvents.push({
                        id: String(feature.id || properties.url || properties.time),
                        magnitude: typeof properties.mag === "number" ? properties.mag : null,
                        place: String(properties.place || tr("unknown")),
                        time: properties.time,
                        depth: coordinates[2],
                        longitude: coordinates[0],
                        latitude: coordinates[1],
                        url: String(properties.url || "https://earthquake.usgs.gov/earthquakes/")
                    })
                })
                validEvents.sort(function(a, b) { return b.time - a.time })
                events = validEvents
                strongest = null
                validEvents.forEach(function(event) {
                    if (event.magnitude !== null
                            && (!strongest || event.magnitude > strongest.magnitude)) {
                        strongest = event
                    }
                })
                generatedAt = response.metadata && response.metadata.generated
                        ? new Date(response.metadata.generated)
                        : null
                errorMessage = ""
            } catch (error) {
                errorMessage = tr("readError")
            }
        }
        request.ontimeout = function() {
            if (activeRequest !== request)
                return
            activeRequest = null
            loading = false
            errorMessage = tr("timeout")
        }
        request.onerror = function() {
            if (activeRequest !== request)
                return
            activeRequest = null
            loading = false
            errorMessage = tr("unavailable")
        }
        request.send()
    }

    function magnitudeColor(magnitude) {
        if (magnitude === null)
            return "#59e1d0"
        if (magnitude >= 6)
            return "#ff667a"
        if (magnitude >= 4)
            return "#ff9a57"
        if (magnitude >= 2.5)
            return "#ffd166"
        return "#59e1d0"
    }

    function openEvent(url) {
        if (url.indexOf("https://earthquake.usgs.gov/") === 0)
            Qt.openUrlExternally(url)
    }

    Timer {
        interval: 30000
        repeat: true
        running: true
        onTriggered: root.refreshFeed()
    }

    Component.onCompleted: refreshFeed()

    compactRepresentation: Item {
        implicitWidth: 150
        implicitHeight: 36
        LayoutMirroring.enabled: root.language === "ar"
        LayoutMirroring.childrenInherit: true

        RowLayout {
            anchors.fill: parent
            spacing: 7

            Rectangle {
                Layout.preferredWidth: 8
                Layout.preferredHeight: 8
                radius: 4
                color: root.errorMessage ? "#ff9a57" : "#59e1d0"
                Layout.alignment: Qt.AlignVCenter
            }

            QQC2.Label {
                Layout.fillWidth: true
                text: root.loading ? root.tr("loading")
                      : root.strongest && root.strongest.magnitude !== null
                        ? "M " + root.strongest.magnitude.toFixed(1) + " · " + root.events.length
                        : root.tr("appTitle") + " · " + root.events.length
                color: "#e5eef3"
                font.bold: true
                elide: Text.ElideRight
            }
        }

        MouseArea {
            anchors.fill: parent
            onClicked: root.expanded = !root.expanded
        }
    }

    fullRepresentation: Item {
        implicitWidth: 380
        implicitHeight: 460
        Layout.minimumWidth: 320
        Layout.minimumHeight: 360
        LayoutMirroring.enabled: root.language === "ar"
        LayoutMirroring.childrenInherit: true

        Rectangle {
            anchors.fill: parent
            radius: 16
            color: "#0c151d"
            border.color: "#1d3440"
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 11

            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                Rectangle {
                    Layout.preferredWidth: 36
                    Layout.preferredHeight: 36
                    radius: 11
                    color: "#123039"
                    border.color: "#28616a"
                    QQC2.Label {
                        anchors.centerIn: parent
                        text: "⌁"
                        color: "#59e1d0"
                        font.pixelSize: 26
                        font.bold: true
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1
                    QQC2.Label {
                        text: root.tr("appTitle")
                        color: "#e5eef3"
                        font.pixelSize: 15
                        font.bold: true
                    }
                    QQC2.Label {
                        text: root.tr("headline")
                        color: "#7f96a4"
                        font.pixelSize: 9
                    }
                }

                QQC2.Label {
                    text: root.errorMessage ? root.tr("offline") : root.tr("live")
                    color: root.errorMessage ? "#ff9a57" : "#59e1d0"
                    font.pixelSize: 10
                    font.bold: true
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 125
                radius: 12
                color: "#11242c"
                border.color: "#1c3e45"

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 10

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        QQC2.Label {
                            text: root.tr("pastDay")
                            color: "#8ba0ad"
                            font.pixelSize: 10
                            font.bold: true
                        }
                        QQC2.Label {
                            text: root.loading ? "…" : root.events.length.toLocaleString()
                            color: "#59e1d0"
                            font.pixelSize: 37
                            font.bold: true
                        }
                        QQC2.Label {
                            text: root.tr("reported")
                            color: "#8195a5"
                            font.pixelSize: 11
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: 1
                        Layout.fillHeight: true
                        color: "#25434b"
                    }

                    ColumnLayout {
                        Layout.preferredWidth: 115
                        spacing: 4
                        QQC2.Label {
                            text: root.tr("strongest")
                            color: "#8ba0ad"
                            font.pixelSize: 9
                            font.bold: true
                        }
                        QQC2.Label {
                            text: root.strongest
                                  ? "M " + root.strongest.magnitude.toFixed(1) : "—"
                            color: root.strongest
                                   ? root.magnitudeColor(root.strongest.magnitude) : "#8195a5"
                            font.pixelSize: 26
                            font.bold: true
                        }
                        QQC2.Label {
                            Layout.fillWidth: true
                            text: root.strongest ? root.strongest.place : root.tr("awaiting")
                            color: "#c5d2d8"
                            font.pixelSize: 9
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                QQC2.Label {
                    Layout.fillWidth: true
                    text: root.tr("latest")
                    color: "#dce8ed"
                    font.pixelSize: 12
                    font.bold: true
                }
                QQC2.ToolButton {
                    text: "↻"
                    font.pixelSize: 20
                    implicitWidth: 32
                    implicitHeight: 32
                    onClicked: root.refreshFeed()
                    QQC2.ToolTip.text: root.tr("refresh")
                    QQC2.ToolTip.visible: hovered
                }
            }

            ListView {
                id: eventList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 3
                model: root.events.slice(0, 12)

                delegate: Item {
                    required property var modelData
                    width: eventList.width
                    height: 45

                    Rectangle {
                        anchors.fill: parent
                        radius: 8
                        color: mouseArea.containsMouse ? "#162a34" : "transparent"
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 7
                        anchors.rightMargin: 7
                        spacing: 9

                        Rectangle {
                            Layout.preferredWidth: 48
                            Layout.preferredHeight: 27
                            radius: 7
                            color: Qt.rgba(root.magnitudeColor(modelData.magnitude).r,
                                           root.magnitudeColor(modelData.magnitude).g,
                                           root.magnitudeColor(modelData.magnitude).b, 0.13)
                            QQC2.Label {
                                anchors.centerIn: parent
                                text: modelData.magnitude === null
                                      ? "M —" : "M " + modelData.magnitude.toFixed(1)
                                color: root.magnitudeColor(modelData.magnitude)
                                font.pixelSize: 11
                                font.bold: true
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            QQC2.Label {
                                Layout.fillWidth: true
                                text: modelData.place
                                color: "#e1eaee"
                                font.pixelSize: 10
                                elide: Text.ElideRight
                            }
                            QQC2.Label {
                                text: Qt.formatDateTime(new Date(modelData.time), "hh:mm")
                                      + "  ·  " + modelData.depth.toFixed(1) + " km " + root.tr("depth")
                                color: "#7f96a4"
                                font.pixelSize: 9
                            }
                        }

                        QQC2.Label {
                            text: "›"
                            color: "#64808d"
                            font.pixelSize: 18
                        }
                    }

                    MouseArea {
                        id: mouseArea
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: root.openEvent(modelData.url)
                    }
                }

                QQC2.Label {
                    anchors.centerIn: parent
                    visible: !root.loading && root.events.length === 0
                    text: root.errorMessage || root.tr("noEvents")
                    color: "#8195a5"
                    font.pixelSize: 11
                }
            }

            RowLayout {
                Layout.fillWidth: true
                QQC2.Label {
                    Layout.fillWidth: true
                    text: root.generatedAt
                          ? root.tr("feed") + " · " + Qt.formatDateTime(root.generatedAt, "hh:mm:ss")
                          : root.tr("source")
                    color: "#617885"
                    font.pixelSize: 9
                }
                QQC2.Label {
                    text: i18n("30s")
                    color: "#59e1d0"
                    font.pixelSize: 9
                    font.bold: true
                }
            }
        }
    }
}
