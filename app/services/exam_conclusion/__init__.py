from datetime import datetime, timezone
from pymongo import UpdateOne

from app.models.paper import Paper
from app.models.exam import Exam, ExamStatus
from app.models.test_attempt import TestAttempt, TestStatus
from app.services.scheduler import schedule_at, get_queue


def conclude_exam(exam_id: str) -> None:
    """
    Compute ranks/percentiles for an exam at scale using streaming and batched writes.
    """
    exam: Exam | None = Exam.objects(id=exam_id).first()
    if not exam:
        raise ValueError(f"Exam not found: {exam_id}")

    collection = TestAttempt._get_collection()

    # Only attempts that were started or completed are considered.
    active_statuses = [TestStatus.IN_PROGRESS.value, TestStatus.COMPLETED.value]
    total_attempts: int = collection.count_documents({"exam": exam.id, "status": {"$in": active_statuses}})
    if total_attempts == 0:
        exam.concluded_on = datetime.now(timezone.utc)
        exam.attempted_count = 0
        exam.highest_score = 0
        exam.lowest_score = 0
        exam.max_score = int(exam.paper.max_score or 0) if getattr(exam, "paper", None) else 0
        exam.save()
        return

    # Overall ranks/percentiles - stream sorted by total_score desc
    overall_cursor = collection.aggregate([
        {"$match": {"exam": exam.id, "status": {"$in": active_statuses}}},
        {"$project": {"total_score": {"$toInt": {"$ifNull": ["$total_score", 0]}}, }},
        {"$sort": {"total_score": -1}},
    ], allowDiskUse=True)

    batch_size = 5000
    operations: list[UpdateOne] = []
    
    idx = 0
    current_rank = 0
    prev_score = None
    highest_score = None
    lowest_score = None
    for doc in overall_cursor:
        attempt_id = doc.get("_id")
        total_score = int(doc.get("total_score") or 0)
        if highest_score is None:
            highest_score = total_score
        lowest_score = total_score
        if prev_score is None or total_score < prev_score:
            current_rank = idx
            prev_score = total_score
        percentile = round(100.0 * (total_attempts - current_rank) / total_attempts, 4)
        
        idx += 1
        operations.append(UpdateOne(
            {"_id": attempt_id}, 
            {"$set": {"rank": current_rank + 1, "percentile": percentile}},
        ))
        if len(operations) >= batch_size:
            collection.bulk_write(operations, ordered=False)
            operations.clear()
    if operations:
        collection.bulk_write(operations, ordered=False)
        operations.clear()

    # Subject-wise ranks/percentiles: iterate subjects from paper definition
    paper: Paper | None = exam.paper
    subjects = [ps.subject_code for ps in (getattr(paper, "subject_max_scores", []) or [])]
    for subj in subjects:
        # Count entries with that subject present among active attempts
        subj_total = collection.count_documents({
            "exam": exam.id,
            "status": {"$in": active_statuses},
            "subject_scores.subject_code": subj,
        })
        if subj_total == 0:
            continue
        cursor = collection.aggregate([
            {"$match": {"exam": exam.id, "status": {"$in": active_statuses}}},
            {"$unwind": "$subject_scores"},
            {"$match": {"subject_scores.subject_code": subj}},
            {"$project": {"s": {"$toInt": {"$ifNull": ["$subject_scores.total_score", 0]} }}},
            {"$sort": {"s": -1}},
        ], allowDiskUse=True)

        idx = 0
        current_rank = 0
        prev_score = None
        for doc in cursor:
            attempt_id = doc.get("_id")
            s = int(doc.get("s") or 0)
            idx += 1
            if prev_score is None or s < prev_score:
                current_rank = idx
                prev_score = s
            percentile = round(100.0 * (subj_total - current_rank) / subj_total, 4)
            # Update embedded element for this subject via arrayFilters
            operations.append(UpdateOne(
                {"_id": attempt_id},
                {"$set": {"subject_scores.$[elem].rank": current_rank, "subject_scores.$[elem].percentile": percentile}},
                array_filters=[{"elem.subject_code": subj}],
            ))
            if len(operations) >= batch_size:
                collection.bulk_write(operations, ordered=False)
                operations.clear()
        if operations:
            collection.bulk_write(operations, ordered=False)
            operations.clear()

    # Exam aggregates
    exam.attempted_count = total_attempts
    exam.highest_score = int(highest_score or 0)
    exam.lowest_score = int(lowest_score or 0)
    if paper:
        exam.max_score = sum(int(pq.positive_score or 0) for pq in paper.paper_questions)
    exam.concluded_on = datetime.now(timezone.utc)
    exam.save()
    print({
        "exam_id": str(exam.id),
        "max_score": exam.max_score,
        "lowest_score": exam.lowest_score,
        "highest_score": exam.highest_score,
        "attempted_count": exam.attempted_count,
        "concluded_on": exam.concluded_on.isoformat() if exam.concluded_on else None,
    })


def mark_exam_started(exam_id: str) -> None:
    exam: Exam | None = Exam.objects(id=exam_id).first()
    if not exam:
        return
    now = datetime.now(timezone.utc)
    if exam.status == ExamStatus.UPCOMING.value and exam.start_time <= now < exam.end_time:
        exam.status = ExamStatus.ONGOING.value
        exam.save()


def mark_exam_ended(exam_id: str) -> None:
    exam: Exam | None = Exam.objects(id=exam_id).first()
    if not exam:
        return
    now = datetime.now(timezone.utc)
    if exam.status == ExamStatus.ONGOING.value and exam.end_time <= now:
        exam.status = ExamStatus.COMPLETED.value
        exam.save()
        get_queue().enqueue(conclude_exam, str(exam.id))


def schedule_exam_jobs(exam: Exam) -> None:
    if exam.start_time and exam.status == ExamStatus.UPCOMING.value:
        schedule_at(exam.start_time, mark_exam_started, str(exam.id))
    if exam.end_time:
        schedule_at(exam.end_time, mark_exam_ended, str(exam.id))
