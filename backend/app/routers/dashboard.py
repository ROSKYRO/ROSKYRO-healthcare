from datetime import timedelta
from fastapi import APIRouter, HTTPException, Depends

from app.db import (
    appointments, tasks, approvals, reviews, visibility_score_history,
    marketing_performance, reports, referrals, queue_entries, patient_followups,
    invoices, partners, statements, organizations, settlements, users,
)
from app.auth import get_current_user, require_internal
from app.utils.ids import now, to_out_many

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/customer")
async def customer_dashboard(current_user: dict = Depends(get_current_user)):
    """The ONE call that fills the entire customer-facing home screen (per
    master prompt: keep this dashboard extremely simple -- only
    business-value widgets, nothing technical)."""
    if current_user["appShell"] != "customer":
        raise HTTPException(status_code=403, detail="Customer dashboard only.")
    org_id = current_user["orgId"]
    this_month = now().strftime("%Y-%m")
    pillars = current_user.get("activePillars") or set()
    has_grow = "grow" in pillars
    has_manage = "manage" in pillars
    has_connect = "connect" in pillars

    today_str = now().date().isoformat()
    today_appts = await appointments.find({"org_id": org_id, "appointment_date": today_str}).sort("appointment_time", 1).to_list(None)
    new_patients_month = await appointments.count_documents({
        "org_id": org_id, "is_new_patient": True,
        "appointment_date": {"$regex": f"^{this_month}"},
    })
    completed_appts_month = await appointments.find({
        "org_id": org_id, "appointment_date": {"$regex": f"^{this_month}"}, "status": "completed",
    }).to_list(None)
    revenue_month = sum(float(a.get("revenue_amount") or 0) for a in completed_appts_month)
    completed_tasks_month = await tasks.count_documents({
        "org_id": org_id, "status": "done",
        "completed_at": {"$gte": now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)},
    })

    response = {
        "activePillars": list(pillars),
        "todaysAppointments": to_out_many(today_appts),
        "newPatientsThisMonth": new_patients_month,
        "revenueThisMonth": revenue_month,
        "completedWorkThisMonth": completed_tasks_month,
        "pendingApprovals": [],
        "reviews": None,
        "visibilityScore": None,
        "marketingPerformance": [],
        "latestMonthlyReport": None,
        "referralsSummary": None,
        "manageSnapshot": None,
    }

    pending_approvals = await approvals.find({"org_id": org_id, "status": "pending"}).sort("created_at", -1).to_list(None)
    response["pendingApprovals"] = to_out_many(pending_approvals)

    if has_grow:
        # Aggregate the average/count in Mongo instead of pulling every
        # review document for this org over the wire just to average one
        # field in Python -- a business with years of reviews would
        # otherwise ship thousands of full documents on every single
        # dashboard load just to compute two numbers.
        review_agg = await reviews.aggregate([
            {"$match": {"org_id": org_id}},
            {"$group": {"_id": None, "avg_rating": {"$avg": "$rating"}, "total": {"$sum": 1}}},
        ]).to_list(None)
        avg_rating = round(review_agg[0]["avg_rating"] or 0, 2) if review_agg else 0
        total_reviews = review_agg[0]["total"] if review_agg else 0
        response["reviews"] = {"average": avg_rating, "total": total_reviews}

        vis_list = await visibility_score_history.find({"org_id": org_id}).sort("period_month", -1).limit(1).to_list(None)
        response["visibilityScore"] = to_out_many(vis_list)[0] if vis_list else None

        mp = await marketing_performance.find({"org_id": org_id, "period_month": this_month}).to_list(None)
        by_channel: dict = {}
        for row in mp:
            ch = by_channel.setdefault(row["channel"], {"channel": row["channel"], "impressions": 0, "clicks": 0, "leads": 0})
            ch["impressions"] += row.get("impressions") or 0
            ch["clicks"] += row.get("clicks") or 0
            ch["leads"] += row.get("leads") or 0
        response["marketingPerformance"] = list(by_channel.values())

        latest_report = await reports.find({"org_id": org_id}).sort("period_month", -1).limit(1).to_list(None)
        response["latestMonthlyReport"] = to_out_many(latest_report)[0] if latest_report else None

    if has_connect:
        # Same aggregation-instead-of-fetch-everything fix as the reviews
        # average above -- this only ever needs a count per status, not
        # every referral document this org has ever sent.
        status_agg = await referrals.aggregate([
            {"$match": {"referring_org_id": org_id}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]).to_list(None)
        response["referralsSummary"] = [{"status": r["_id"], "count": r["count"]} for r in status_agg]

    if has_manage:
        queue_waiting = await queue_entries.count_documents({
            "org_id": org_id, "status": "waiting",
            "checked_in_at": {"$gte": now().replace(hour=0, minute=0, second=0, microsecond=0)},
        })
        followups_due = await patient_followups.count_documents({
            "org_id": org_id, "status": "pending", "due_date": {"$lte": today_str},
        })
        unpaid_agg = await invoices.aggregate([
            {"$match": {"org_id": org_id, "status": {"$in": ["sent", "overdue"]}}},
            {"$group": {"_id": None, "n": {"$sum": 1}, "total": {"$sum": "$total"}}},
        ]).to_list(None)
        response["manageSnapshot"] = {
            "queueWaiting": queue_waiting,
            "followupsDue": followups_due,
            "unpaidInvoices": unpaid_agg[0]["n"] if unpaid_agg else 0,
            "unpaidInvoicesTotal": float(unpaid_agg[0]["total"] or 0) if unpaid_agg else 0.0,
        }

    return response


@router.get("/partner")
async def partner_dashboard(current_user: dict = Depends(get_current_user)):
    if current_user["appShell"] != "partner":
        raise HTTPException(status_code=403, detail="Partner dashboard only.")
    partner = await partners.find_one({"org_id": current_user["orgId"]})
    if not partner:
        raise HTTPException(status_code=404, detail="Partner profile not found for this account.")

    incoming = await referrals.count_documents({"partner_id": partner["_id"], "status": "sent"})

    org_partner_ids = [p["_id"] async for p in partners.find({"org_id": current_user["orgId"]})]
    outgoing = await referrals.count_documents({
        "partner_id": {"$in": org_partner_ids},
        "status": {"$nin": ["completed", "cancelled", "declined"]},
    })
    pending = await referrals.count_documents({"partner_id": partner["_id"], "status": {"$in": ["sent", "accepted", "in_progress"]}})
    completed = await referrals.count_documents({"partner_id": partner["_id"], "status": "completed"})
    stmts = await statements.find({"party_type": "partner", "party_id": partner["_id"]}).sort("period_month", -1).limit(6).to_list(None)

    from app.utils.ids import to_out
    return {
        "partner": to_out(partner),
        "incomingRequests": incoming,
        "pendingRequests": pending,
        "completedRequests": completed,
        "statements": to_out_many(stmts),
    }


@router.get("/internal", dependencies=[Depends(require_internal)])
async def internal_dashboard(current_user: dict = Depends(get_current_user)):
    org_count = await organizations.count_documents({"status": "active"})
    partner_count = await partners.count_documents({"verification_status": "verified"})
    pending_verifications = await partners.count_documents({"verification_status": "pending"})
    open_tasks = await tasks.count_documents({"status": {"$ne": "done"}})
    overdue_tasks = await tasks.count_documents({"status": {"$ne": "done"}, "sla_due_at": {"$lt": now()}})

    # Both queries below are platform-wide (no org_id filter), so they only
    # ever grow with total referral/settlement volume across every business
    # on ROSKYRO -- fetching every matching document just to count/sum in
    # Python would get steadily slower as the platform grows, purely from
    # this one internal dashboard load. Aggregating in Mongo keeps this a
    # fixed-cost query regardless of how many referrals/settlements exist.
    since = now() - timedelta(days=14)
    day_agg = await referrals.aggregate([
        {"$match": {"created_at": {"$gt": since}}},
        {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}, "n": {"$sum": 1}}},
    ]).to_list(None)
    referral_volume = sorted(({"day": r["_id"], "n": r["n"]} for r in day_agg), key=lambda x: x["day"])

    settlement_agg = await settlements.aggregate([
        {"$match": {"status": "pending"}},
        {"$group": {"_id": None, "n": {"$sum": 1}, "total": {"$sum": "$amount"}}},
    ]).to_list(None)
    pending_settlements = {
        "n": settlement_agg[0]["n"] if settlement_agg else 0,
        "total": float(settlement_agg[0]["total"] or 0) if settlement_agg else 0.0,
    }

    my_open = await tasks.count_documents({"assigned_to": current_user["id"], "status": {"$ne": "done"}})
    my_overdue = await tasks.count_documents({"assigned_to": current_user["id"], "status": {"$ne": "done"}, "sla_due_at": {"$lt": now()}})

    return {
        "activeOrganizations": org_count,
        "verifiedPartners": partner_count,
        "pendingPartnerVerifications": pending_verifications,
        "openTasks": open_tasks,
        "overdueTasks": overdue_tasks,
        "referralVolumeLast14Days": referral_volume,
        "pendingSettlements": pending_settlements,
        "myQueue": {"open": my_open, "overdue": my_overdue},
    }
