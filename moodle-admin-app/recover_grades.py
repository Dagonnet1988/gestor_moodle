"""Utility to rebuild missing grade_grades records from quiz attempts.

Run from the venv root directory:

    .\venv\Scripts\activate
    python recover_grades.py 31    # course id

The script walks through all quiz grade items in the given course, finds the
highest finished attempt for each user, and inserts a corresponding row into
mdl_grade_grades when one does not already exist.  You can adapt or extend it
for other types of grade items if necessary.

This is only a fallback; the preferred mechanism is to use Moodle's own
"Recalculate" button or CLI script (see comments below)."""

import sys
from app.services.db import execute_query, execute_insert


def recover_course(courseid: int):
    # find quiz-related grade items for the course
    quiz_items = execute_query(
        """
        SELECT gi.id AS itemid, q.id AS quizid, q.name
        FROM mdl_grade_items gi
        JOIN mdl_quiz q ON q.id = gi.iteminstance AND gi.itemmodule='quiz'
        WHERE gi.courseid=%s
        """,
        (courseid,)
    )

    if not quiz_items:
        print(f"no quiz grade items found for course {courseid}")
        return

    for item in quiz_items:
        itemid = item["itemid"]
        quizid = item["quizid"]
        print(f"processing quiz '{item['name']}' (quizid={quizid}, itemid={itemid})")

        # best finished attempt per user
        attempts = execute_query(
            """
            SELECT userid, MAX(sumgrades) AS grade
            FROM mdl_quiz_attempts
            WHERE quiz=%s AND state='finished'
            GROUP BY userid
            """,
            (quizid,)
        )

        for a in attempts:
            userid = a["userid"]
            grade = a["grade"] or 0
            # skip if there is already a grade recorded
            existing = execute_query(
                "SELECT id FROM mdl_grade_grades WHERE itemid=%s AND userid=%s",
                (itemid, userid),
            )
            if existing:
                continue
            execute_insert(
                """
                INSERT INTO mdl_grade_grades
                    (itemid, userid, rawgrade, finalgrade, feedback, feedbackformat)
                VALUES (%s, %s, %s, %s, '', 0)
                """,
                (itemid, userid, grade, grade),
            )
            print(f"  inserted grade {grade} for user {userid}")


def main():
    if len(sys.argv) != 2:
        print("usage: python recover_grades.py <courseid>")
        sys.exit(1)
    recover_course(int(sys.argv[1]))


if __name__ == "__main__":
    main()
