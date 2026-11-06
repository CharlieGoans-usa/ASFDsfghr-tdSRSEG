var REPORT_WEBHOOK_URL = "REDACTION";

// ============================================
// BOINGUS MODERATION - CLOUDSCRIPT
// ============================================

var STAFF_RANKS = {
    "67FEE4A538774F7E": "Owner",
    "": "Staff",
    "": "Moderator",
    "": "Trial Moderator"
};

var ALLOW_SELF_REPORTING = false;

var REPORT_PRIORITIES = {
    "Player": "Normal",
    "Trial Moderator": "Medium",
    "Moderator": "High",
    "Staff": "Critical",
    "Owner": "Critical"
};

var VALID_REPORT_REASONS = [
    "Harassment",
    "Exploiting",
    "Cheating",
    "Toxicity",
    "Inappropriate Username",
    "Other"
];

// Save the full report as a separate Title Internal Data key.
// This provides a central index the local Python panel can retrieve.
// Keep report values small; do not store webhook responses or secrets here.
function storeReportForPanel(report) {
    var key = "BOINGUS_Report_" + report.reportID;
    server.SetTitleInternalData({
        Key: key,
        Value: JSON.stringify(report)
    });

    // Also attach the report ID to the target player's private server-only data.
    // This makes it possible to retrieve reports from an individual player profile.
    var existing = server.GetUserInternalData({
        PlayFabId: report.targetPlayFabID,
        Keys: ["BOINGUS_ReportIDs"]
    });

    var ids = [];
    if (existing.Data &&
        existing.Data.BOINGUS_ReportIDs &&
        existing.Data.BOINGUS_ReportIDs.Value) {
        try {
            ids = JSON.parse(existing.Data.BOINGUS_ReportIDs.Value) || [];
        } catch (e) {
            ids = [];
        }
    }

    if (ids.indexOf(report.reportID) === -1) {
        ids.push(report.reportID);
    }

    server.UpdateUserInternalData({
        PlayFabId: report.targetPlayFabID,
        Data: {
            BOINGUS_ReportIDs: JSON.stringify(ids),
            BOINGUS_ReportCount: String(ids.length),
            BOINGUS_LastReportAt: report.timestamp
        }
    });
}

handlers.SubmitReport = function (args, context) {
    var reporterID = currentPlayerId;

    if (!reporterID) {
        throw "Unable to identify reporting player.";
    }

    if (!args || !args.targetPlayFabID || !args.reason) {
        throw "Missing report information.";
    }

    var targetID = String(args.targetPlayFabID).trim();
    var targetUsername = String(args.targetUsername || "Unknown").substring(0, 64);
    var reason = String(args.reason).trim();

    if (targetID.length < 5 || targetID.length > 64) {
        throw "Invalid target PlayFab ID.";
    }

    if (!ALLOW_SELF_REPORTING && targetID === reporterID) {
        throw "You cannot report yourself.";
    }

    if (VALID_REPORT_REASONS.indexOf(reason) === -1) {
        throw "Invalid report reason.";
    }

    var staffRank = STAFF_RANKS[reporterID] || "Player";
    var priority = REPORT_PRIORITIES[staffRank] || "Normal";
    var timestamp = new Date().toISOString();

    var report = {
        reportID: "RPT-" + new Date().getTime() + "-" + reporterID,
        targetPlayFabID: targetID,
        targetUsername: targetUsername,
        reporterPlayFabID: reporterID,
        reporterRank: staffRank,
        reason: reason,
        priority: priority,
        timestamp: timestamp,
        lobbyID: String(args.lobbyID || "Unknown").substring(0, 100),
        photonRegion: String(args.photonRegion || "Unknown").substring(0, 32),
        status: "Pending"
    };

    // Persist to PlayFab before attempting Discord delivery.
    // If Discord is temporarily unavailable, the moderation record still exists.
    try {
        storeReportForPanel(report);
    } catch (storageError) {
        log.error("REPORT STORAGE ERROR: " + storageError);
        throw "Report could not be saved. Please try again.";
    }

    var discordPayload = {
        username: "BOINGUS Report System",
        embeds: [{
            title: "New Player Report",
            color: priority === "Critical" ? 15158332 :
                   priority === "High" ? 15105570 :
                   priority === "Medium" ? 16776960 : 3447003,
            fields: [
                { name: "Reported Player", value: targetUsername + "\n`" + targetID + "`", inline: false },
                { name: "Reporter", value: "`" + reporterID + "`", inline: true },
                { name: "Reporter Rank", value: staffRank, inline: true },
                { name: "Priority", value: priority, inline: true },
                { name: "Reason", value: reason, inline: true },
                { name: "Lobby", value: report.lobbyID, inline: true },
                { name: "Photon Region", value: report.photonRegion, inline: true },
                { name: "Report ID", value: "`" + report.reportID + "`", inline: false },
                { name: "Submitted", value: timestamp, inline: false }
            ],
            footer: { text: "BOINGUS Moderation System" }
        }]
    };

    try {
        var response = http.request(
            REPORT_WEBHOOK_URL,
            "post",
            JSON.stringify(discordPayload),
            "application/json",
            {}
        );

        log.info("REPORT SUCCESS: " + report.reportID + " | Target: " + targetID);
        log.info("Discord webhook response: " + response);

        return {
            success: true,
            message: "Report submitted successfully.",
            reportID: report.reportID,
            priority: priority
        };
    } catch (error) {
        // Report is already persisted in PlayFab. Do not discard it just because
        // the optional Discord notification failed.
        log.error("REPORT WEBHOOK ERROR: " + error);
        return {
            success: true,
            message: "Report saved, but Discord notification failed.",
            reportID: report.reportID,
            priority: priority,
            discordNotificationFailed: true
        };
    }
};
