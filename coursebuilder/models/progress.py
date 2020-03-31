# Copyright 2012 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Student progress trackers."""

__author__ = 'Sean Lip (sll@google.com)'

import datetime
import logging
import os

import courses
import transforms

from models import QuestionDAO
from models import QuestionGroupDAO
from models import StudentPropertyEntity
from tools import verify


# Names of component tags that are tracked for progress calculations.
TRACKABLE_COMPONENTS = [
    'question',
    'question-group',
]


class UnitLessonCompletionTracker(object):
    """Tracks student completion for a unit/lesson-based linear course."""

    PROPERTY_KEY = 'linear-course-completion'

    # Here are representative examples of the keys for the various entities
    # used in this class:
    #   Unit 1: u.1
    #   Unit 1, Lesson 1: u.1.l.1
    #   Unit 1, Lesson 1, Activity 0: u.1.l.1.a.0
    #   Unit 1, Lesson 1, Activity 0, Block 4: u.1.l.1.a.0.b.4
    #   Assessment 'Pre': s.Pre
    # At the moment, we do not divide assessments into blocks.
    #
    # The following keys were added in v1.5:
    #   Unit 1, Lesson 1, HTML: u.1.l.1.h.0
    #   Unit 1, Lesson 1, HTML, Component with instanceid id: u.1.l.1.h.0.c.id
    #
    # The number after the 'h' and 'a' codes is always zero, since a lesson may
    # have at most one HTML body and one activity.
    #
    # IMPORTANT NOTE: The values of the keys mean different things depending on
    # whether the entity is a composite entity or not.
    # If it is a composite entity (unit, lesson, activity), then the value is
    #   - 0 if none of its sub-entities has been completed
    #   - 1 if some, but not all, of its sub-entities have been completed
    #   - 2 if all its sub-entities have been completed.
    # If it is not a composite entity (i.e. block, assessment, component), then
    # the value is just the number of times the event has been triggered.

    # Constants for recording the state of composite entities.
    # TODO(sll): Change these to enums.
    NOT_STARTED_STATE = 0
    IN_PROGRESS_STATE = 1
    COMPLETED_STATE = 2

    MULTIPLE_CHOICE = 'multiple choice'
    MULTIPLE_CHOICE_GROUP = 'multiple choice group'
    QUESTION_GROUP = 'question-group'
    QUESTION = 'question'

    EVENT_CODE_MAPPING = {
        'unit': 'u',
        'lesson': 'l',
        'activity': 'a',
        'html': 'h',
        'block': 'b',
        'assessment': 's',
        'component': 'c',
    }
    COMPOSITE_ENTITIES = [
        EVENT_CODE_MAPPING['unit'],
        EVENT_CODE_MAPPING['lesson'],
        EVENT_CODE_MAPPING['activity'],
        EVENT_CODE_MAPPING['html']
    ]

    def __init__(self, course):
        self._course = course

    def _get_course(self):
        return self._course

    def get_activity_as_python(self, unit_id, lesson_id):
        """Gets the corresponding activity as a Python object."""
        root_name = 'activity'
        course = self._get_course()
        activity_text = course.app_context.fs.get(
            os.path.join(course.app_context.get_home(),
                         course.get_activity_filename(unit_id, lesson_id)))
        content, noverify_text = verify.convert_javascript_to_python(
            activity_text, root_name)
        activity = verify.evaluate_python_expression_from_text(
            content, root_name, verify.Activity().scope, noverify_text)
        return activity

    def _get_unit_key(self, unit_id):
        return '%s.%s' % (self.EVENT_CODE_MAPPING['unit'], unit_id)

    def _get_lesson_key(self, unit_id, lesson_id):
        return '%s.%s.%s.%s' % (
            self.EVENT_CODE_MAPPING['unit'], unit_id,
            self.EVENT_CODE_MAPPING['lesson'], lesson_id
        )

    def _get_activity_key(self, unit_id, lesson_id):
        return '%s.%s.%s.%s.%s.%s' % (
            self.EVENT_CODE_MAPPING['unit'], unit_id,
            self.EVENT_CODE_MAPPING['lesson'], lesson_id,
            self.EVENT_CODE_MAPPING['activity'], 0
        )

    def _get_html_key(self, unit_id, lesson_id):
        return '%s.%s.%s.%s.%s.%s' % (
            self.EVENT_CODE_MAPPING['unit'], unit_id,
            self.EVENT_CODE_MAPPING['lesson'], lesson_id,
            self.EVENT_CODE_MAPPING['html'], 0
        )

    def _get_component_key(self, unit_id, lesson_id, component_id):
        return '%s.%s.%s.%s.%s.%s.%s.%s' % (
            self.EVENT_CODE_MAPPING['unit'], unit_id,
            self.EVENT_CODE_MAPPING['lesson'], lesson_id,
            self.EVENT_CODE_MAPPING['html'], 0,
            self.EVENT_CODE_MAPPING['component'], component_id
        )

    def _get_block_key(self, unit_id, lesson_id, block_id):
        return '%s.%s.%s.%s.%s.%s.%s.%s' % (
            self.EVENT_CODE_MAPPING['unit'], unit_id,
            self.EVENT_CODE_MAPPING['lesson'], lesson_id,
            self.EVENT_CODE_MAPPING['activity'], 0,
            self.EVENT_CODE_MAPPING['block'], block_id
        )

    def _get_assessment_key(self, assessment_id):
        return '%s.%s' % (self.EVENT_CODE_MAPPING['assessment'], assessment_id)

    def get_entity_type_from_key(self, progress_entity_key):
        return progress_entity_key.split('.')[-2]

    def determine_if_composite_entity(self, progress_entity_key):
        return self.get_entity_type_from_key(
            progress_entity_key) in self.COMPOSITE_ENTITIES

    def get_valid_component_ids(self, unit_id, lesson_id):
        """Returns a list of cpt ids representing trackable components."""
        components = []
        for cpt_name in TRACKABLE_COMPONENTS:
            all_cpts = self._get_course().get_components_with_name(
                unit_id, lesson_id, cpt_name)
            components += [
                cpt['instanceid'] for cpt in all_cpts if cpt['instanceid']]
        return components

    def get_valid_block_ids(self, unit_id, lesson_id):
        """Returns a list of block ids representing interactive activities."""
        valid_blocks_data = self._get_valid_blocks_data(unit_id, lesson_id)
        return [block[0] for block in valid_blocks_data]

    def get_valid_blocks(self, unit_id, lesson_id):
        """Returns a list of blocks representing interactive activities."""
        valid_blocks_data = self._get_valid_blocks_data(unit_id, lesson_id)
        return [block[1] for block in valid_blocks_data]

    def _get_valid_blocks_data(self, unit_id, lesson_id):
        """Returns a list of (b_id, block) representing trackable activities."""
        valid_blocks = []

        # Check if activity exists before calling get_activity_as_python.
        unit = self._get_course().find_unit_by_id(unit_id)
        lesson = self._get_course().find_lesson_by_id(unit, lesson_id)
        if unit and lesson and lesson.activity:
            # Get the activity corresponding to this unit/lesson combination.
            activity = self.get_activity_as_python(unit_id, lesson_id)
            for block_id in range(len(activity['activity'])):
                block = activity['activity'][block_id]
                if isinstance(block, dict):
                    valid_blocks.append((block_id, block))
        return valid_blocks

    def get_id_to_questions_dict(self):
        """Returns a dict that maps each question to a list of its answers.

        Returns:
            A dict that represents the questions in lessons. The keys of this
            dict are question ids, and the corresponding values are dicts, each
            containing the following five key-value pairs:
            - answers: a list of 0's with length corresponding to number of
                choices a question has.
            - location: str. href value of the location of the question in the
                course.
            - num_attempts: int. Number of attempts for this question. This is
                used as the denominator when calculating the average score for a
                question. This value may differ from the sum of the elements in
                'answers' because of event entities that record an answer but
                not a score.
            - score: int. Aggregated value of the scores.
            - label: str. Human readable identifier for this question.
        """
        id_to_questions = {}
        for unit in self._get_course().get_units_of_type(verify.UNIT_TYPE_UNIT):
            unit_id = unit.unit_id
            for lesson in self._get_course().get_lessons(unit_id):
                lesson_id = lesson.lesson_id
                # Add mapping dicts for questions in old-style activities.
                if lesson.activity:
                    blocks = self._get_valid_blocks_data(unit_id, lesson_id)
                    for block_index, (block_id, block) in enumerate(blocks):
                        if block['questionType'] == self.MULTIPLE_CHOICE:
                            # Old style question.
                            id_to_questions.update(
                                self._create_old_style_question_dict(
                                    block, block_id, block_index, unit, lesson))

                        elif (block['questionType'] ==
                              self.MULTIPLE_CHOICE_GROUP):
                            # Old style multiple choice group.
                            for ind, q in enumerate(block['questionsList']):
                                id_to_questions.update(
                                    self._create_old_style_question_dict(
                                        q, block_id, block_index, unit,
                                        lesson, index=ind))

                # Add mapping dicts for CBv1.5 style questions.
                if lesson.objectives:
                    for cpt in self._get_course().get_question_components(
                            unit_id, lesson_id):
                        # CB v1.5 style questions.
                        id_to_questions.update(
                            self._create_v15_lesson_question_dict(
                                cpt, unit, lesson))

                    for cpt in self._get_course().get_question_group_components(
                            unit_id, lesson_id):
                        # CB v1.5 style question groups.
                        id_to_questions.update(
                            self._create_v15_lesson_question_group_dict(
                                cpt, unit, lesson))

        return id_to_questions

    def get_id_to_assessments_dict(self):
        """Returns a dict that maps each question to a list of its answers.

        Returns:
            A dict that represents the questions in assessments. The keys of
            this dict are question ids, and the corresponding values are dicts,
            each containing the following five key-value pairs:
            - answers: a list of 0's with length corresponding to number of
                choices a question has.
            - location: str. href value of the location of the question in the
                course.
            - num_attempts: int. Number of attempts for this question. This is
                used as the denominator when calculating the average score for a
                question. This value may differ from the sum of the elements in
                'answers' because of event entities that record an answer but
                not a score.
            - score: int. Aggregated value of the scores.
            - label: str. Human readable identifier for this question.
        """
        id_to_assessments = {}
        for assessment in self._get_course().get_assessment_list():
            if not self._get_course().needs_human_grader(assessment):
                assessment_components = self._get_course(
                    ).get_assessment_components(assessment.unit_id)
                # CB v1.5 style assessments.
                for cpt in assessment_components:
                    if cpt['cpt_name'] == self.QUESTION_GROUP:
                        id_to_assessments.update(
                            self._create_v15_assessment_question_group_dict(
                                cpt, assessment))
                    elif cpt['cpt_name'] == self.QUESTION:
                        id_to_assessments.update(
                            self._create_v15_assessment_question_dict(
                                cpt, assessment))

                # Old style javascript assessments.
                try:
                    content = self._get_course().get_assessment_content(
                        assessment)
                    id_to_assessments.update(
                        self._create_old_style_assessment_dict(
                            content['assessment'], assessment))
                except AttributeError:
                    # Assessment file does not exist.
                    continue

        return id_to_assessments

    def _get_link_for_assessment(self, assessment_id):
        return 'assessment?name=%s' % (assessment_id)

    def _get_link_for_activity(self, unit_id, lesson_id):
        return 'activity?unit=%s&lesson=%s' % (unit_id, lesson_id)

    def _get_link_for_lesson(self, unit_id, lesson_id):
        return 'unit?unit=%s&lesson=%s' % (unit_id, lesson_id)

    def _create_v15_question_dict(self, q_id, label, link, num_choices):
        """Returns a dict that represents CB v1.5 style question."""
        return {
            q_id: {
                'answer_counts': [0] * num_choices,
                'label': label,
                'location': link,
                'score': 0,
                'num_attempts': 0
            }
        }

    def _create_v15_lesson_question_dict(self, cpt, unit, lesson):
        try:
            question = QuestionDAO.load(cpt['quid'])
            if question.type == question.MULTIPLE_CHOICE:
                q_id = 'u.%s.l.%s.c.%s' % (
                    unit.unit_id, lesson.lesson_id, cpt['instanceid'])
                label = 'Unit %s Lesson %s, Question %s' % (
                    unit.index, lesson.index, question.description)
                link = self._get_link_for_lesson(unit.unit_id, lesson.lesson_id)
                num_choices = len(question.dict['choices'])
                return self._create_v15_question_dict(
                    q_id, label, link, num_choices)
            else:
                return {}
        except Exception as e:  # pylint: disable-msg=broad-except
            logging.error(
                'Failed to process the question data. '
                'Error: %s, data: %s', e, cpt)
            return {}

    def _create_v15_lesson_question_group_dict(self, cpt, unit, lesson):
        try:
            question_group = QuestionGroupDAO.load(cpt['qgid'])
            questions = {}
            for ind, quid in enumerate(question_group.question_ids):
                question = QuestionDAO.load(quid)
                if question.type == question.MULTIPLE_CHOICE:
                    q_id = 'u.%s.l.%s.c.%s.i.%s' % (
                        unit.unit_id, lesson.lesson_id, cpt['instanceid'], ind)
                    label = ('Unit %s Lesson %s, Question Group %s Question %s'
                             % (unit.index, lesson.index,
                                question_group.description,
                                question.description))
                    link = self._get_link_for_lesson(
                        unit.unit_id, lesson.lesson_id)
                    num_choices = len(question.dict['choices'])
                    questions.update(self._create_v15_question_dict(
                        q_id, label, link, num_choices))
            return questions
        except Exception as e:  # pylint: disable-msg=broad-except
            logging.error(
                'Failed to process the question data. '
                'Error: %s, data: %s', e, cpt)
            return {}

    def _create_v15_assessment_question_group_dict(self, cpt, assessment):
        try:
            question_group = QuestionGroupDAO.load(cpt['qgid'])
            questions = {}
            for ind, quid in enumerate(question_group.question_ids):
                question = QuestionDAO.load(quid)
                if question.type == question.MULTIPLE_CHOICE:
                    q_id = 's.%s.c.%s.i.%s' % (
                        assessment.unit_id, cpt['instanceid'], ind)
                    label = '%s, Question Group %s Question %s' % (
                        assessment.title, question_group.description,
                        question.description)
                    link = self._get_link_for_assessment(assessment.unit_id)
                    num_choices = len(question.dict['choices'])
                    questions.update(
                        self._create_v15_question_dict(
                            q_id, label, link, num_choices))
            return questions
        except Exception as e:  # pylint: disable-msg=broad-except
            logging.error(
                'Failed to process the question data. '
                'Error: %s, data: %s', e, cpt)
            return {}

    def _create_v15_assessment_question_dict(self, cpt, assessment):
        try:
            question = QuestionDAO.load(cpt['quid'])
            if question.type == question.MULTIPLE_CHOICE:
                q_id = 's.%s.c.%s' % (assessment.unit_id, cpt['instanceid'])
                label = '%s, Question %s' % (
                    assessment.title, question.description)
                link = self._get_link_for_assessment(assessment.unit_id)
                num_choices = len(question.dict['choices'])
                return self._create_v15_question_dict(
                    q_id, label, link, num_choices)
            else:
                return {}
        except Exception as e:  # pylint: disable-msg=broad-except
            logging.error(
                'Failed to process the question data. '
                'Error: %s, data: %s', e, cpt)
            return {}

    def _create_old_style_question_dict(self, block, block_id, block_index,
                                        unit, lesson, index=None):
        try:
            if index is not None:
                # Question is in a multiple choice group.
                b_id = 'u.%s.l.%s.b.%s.i.%s' % (
                    unit.unit_id, lesson.lesson_id, block_id, index)
                label = 'Unit %s Lesson %s Activity, Item %s Part %s' % (
                    unit.index, lesson.index, block_index + 1, index + 1)
            else:
                b_id = 'u.%s.l.%s.b.%s' % (
                    unit.unit_id, lesson.lesson_id, block_id)
                label = 'Unit %s Lesson %s Activity, Item %s' % (
                    unit.index, lesson.index, block_index + 1)
            return {
                b_id: {
                    'answer_counts': [0] * len(block['choices']),
                    'label': label,
                    'location': self._get_link_for_activity(
                        unit.unit_id, lesson.lesson_id),
                    'score': 0,
                    'num_attempts': 0
                }
            }
        except Exception as e:  # pylint: disable-msg=broad-except
            logging.error(
                'Failed to process the question data. '
                'Error: %s, data: %s', e, block)
            return {}

    def _create_old_style_assessment_dict(self, content, assessment):
        try:
            questions = {}
            for ind, question in enumerate(content['questionsList']):
                if 'choices' in question:
                    questions.update(
                        {
                            's.%s.i.%s' % (assessment.unit_id, ind): {
                                'answer_counts': [0] * len(question['choices']),
                                'label': '%s, Question %s' % (
                                    assessment.title, ind + 1),
                                'location': self._get_link_for_assessment(
                                    assessment.unit_id),
                                'score': 0,
                                'num_attempts': 0
                            }
                        }
                    )
            return questions
        except Exception as e:  # pylint: disable-msg=broad-except
            logging.error(
                'Failed to process the question data. '
                'Error: %s, data: %s', e, content)
            return {}

    def _update_unit(self, progress, event_key):
        """Updates a unit's progress if all its lessons have been completed."""
        split_event_key = event_key.split('.')
        assert len(split_event_key) == 2
        unit_id = split_event_key[1]

        if self._get_entity_value(progress, event_key) == self.COMPLETED_STATE:
            return

        # Record that at least one lesson in this unit has been completed.
        self._set_entity_value(progress, event_key, self.IN_PROGRESS_STATE)

        # Check if all lessons in this unit have been completed.
        lessons = self._get_course().get_lessons(unit_id)
        for lesson in lessons:
            if (self.get_lesson_status(
                    progress,
                    unit_id, lesson.lesson_id) != self.COMPLETED_STATE):
                return

        # Record that all lessons in this unit have been completed.
        self._set_entity_value(progress, event_key, self.COMPLETED_STATE)

    def _update_lesson(self, progress, event_key):
        """Updates a lesson's progress based on the progress of its children."""
        split_event_key = event_key.split('.')
        assert len(split_event_key) == 4
        unit_id = split_event_key[1]
        lesson_id = split_event_key[3]

        if self._get_entity_value(progress, event_key) == self.COMPLETED_STATE:
            return

        # Record that at least one part of this lesson has been completed.
        self._set_entity_value(progress, event_key, self.IN_PROGRESS_STATE)

        lessons = self._get_course().get_lessons(unit_id)
        for lesson in lessons:
            if str(lesson.lesson_id) == lesson_id and lesson:
                # Is the activity completed?
                if (lesson.activity and self.get_activity_status(
                        progress, unit_id, lesson_id) != self.COMPLETED_STATE):
                    return

                # Are all components of the lesson completed?
                if (self.get_html_status(
                        progress, unit_id, lesson_id) != self.COMPLETED_STATE):
                    return

        # Record that all activities in this lesson have been completed.
        self._set_entity_value(progress, event_key, self.COMPLETED_STATE)

    def _update_activity(self, progress, event_key):
        """Updates activity's progress when all interactive blocks are done."""
        split_event_key = event_key.split('.')
        assert len(split_event_key) == 6
        unit_id = split_event_key[1]
        lesson_id = split_event_key[3]

        if self._get_entity_value(progress, event_key) == self.COMPLETED_STATE:
            return

        # Record that at least one block in this activity has been completed.
        self._set_entity_value(progress, event_key, self.IN_PROGRESS_STATE)

        valid_block_ids = self.get_valid_block_ids(unit_id, lesson_id)
        for block_id in valid_block_ids:
            if not self.is_block_completed(
                    progress, unit_id, lesson_id, block_id):
                return

        # Record that all blocks in this activity have been completed.
        self._set_entity_value(progress, event_key, self.COMPLETED_STATE)

    def _update_html(self, progress, event_key):
        """Updates html's progress when all interactive blocks are done."""
        split_event_key = event_key.split('.')
        assert len(split_event_key) == 6
        unit_id = split_event_key[1]
        lesson_id = split_event_key[3]

        if self._get_entity_value(progress, event_key) == self.COMPLETED_STATE:
            return

        # Record that at least one block in this activity has been completed.
        self._set_entity_value(progress, event_key, self.IN_PROGRESS_STATE)

        cpt_ids = self.get_valid_component_ids(unit_id, lesson_id)
        for cpt_id in cpt_ids:
            if not self.is_component_completed(
                    progress, unit_id, lesson_id, cpt_id):
                return

        # Record that all blocks in this activity have been completed.
        self._set_entity_value(progress, event_key, self.COMPLETED_STATE)

    UPDATER_MAPPING = {
        'activity': _update_activity,
        'html': _update_html,
        'lesson': _update_lesson,
        'unit': _update_unit
    }

    # Dependencies for recording derived events. The key is the current
    # event, and the value is a tuple, each element of which contains:
    # - the dependent entity to be updated
    # - the transformation to apply to the id of the current event to get the
    #       id for the derived parent event
    DERIVED_EVENTS = {
        'block': (
            {
                'entity': 'activity',
                'generate_parent_id': (lambda s: '.'.join(s.split('.')[:-2])),
            },
        ),
        'activity': (
            {
                'entity': 'lesson',
                'generate_parent_id': (lambda s: '.'.join(s.split('.')[:-2])),
            },
        ),
        'lesson': (
            {
                'entity': 'unit',
                'generate_parent_id': (lambda s: '.'.join(s.split('.')[:-2])),
            },
        ),
        'component': (
            {
                'entity': 'html',
                'generate_parent_id': (lambda s: '.'.join(s.split('.')[:-2])),
            },
        ),
        'html': (
            {
                'entity': 'lesson',
                'generate_parent_id': (lambda s: '.'.join(s.split('.')[:-2])),
            },
        ),
    }

    def put_activity_completed(self, student, unit_id, lesson_id):
        """Records that the given student has completed an activity."""
        if not self._get_course().is_valid_unit_lesson_id(unit_id, lesson_id):
            return
        self._put_event(
            student, 'activity', self._get_activity_key(unit_id, lesson_id))

    def put_html_completed(self, student, unit_id, lesson_id):
        """Records that the given student has completed a lesson page."""
        if not self._get_course().is_valid_unit_lesson_id(unit_id, lesson_id):
            return
        self._put_event(
            student, 'html', self._get_html_key(unit_id, lesson_id))

    def put_block_completed(self, student, unit_id, lesson_id, block_id):
        """Records that the given student has completed an activity block."""
        if not self._get_course().is_valid_unit_lesson_id(unit_id, lesson_id):
            return
        if block_id not in self.get_valid_block_ids(unit_id, lesson_id):
            return
        self._put_event(
            student,
            'block',
            self._get_block_key(unit_id, lesson_id, block_id)
        )

    def put_component_completed(self, student, unit_id, lesson_id, cpt_id):
        """Records completion of a component in a lesson body."""
        if not self._get_course().is_valid_unit_lesson_id(unit_id, lesson_id):
            return
        if cpt_id not in self.get_valid_component_ids(unit_id, lesson_id):
            return
        self._put_event(
            student,
            'component',
            self._get_component_key(unit_id, lesson_id, cpt_id)
        )

    def put_assessment_completed(self, student, assessment_id):
        """Records that the given student has completed the given assessment."""
        if not self._get_course().is_valid_assessment_id(assessment_id):
            return
        self._put_event(
            student, 'assessment', self._get_assessment_key(assessment_id))

    def put_activity_accessed(self, student, unit_id, lesson_id):
        """Records that the given student has accessed this activity."""
        # This method currently exists because we need to mark activities
        # without interactive blocks as 'completed' when they are accessed.
        if not self.get_valid_block_ids(unit_id, lesson_id):
            self.put_activity_completed(student, unit_id, lesson_id)

    def put_html_accessed(self, student, unit_id, lesson_id):
        """Records that the given student has accessed this lesson page."""
        # This method currently exists because we need to mark lesson bodies
        # without interactive blocks as 'completed' when they are accessed.
        if not self.get_valid_component_ids(unit_id, lesson_id):
            self.put_html_completed(student, unit_id, lesson_id)

    def _put_event(self, student, event_entity, event_key):
        """Starts a cascade of updates in response to an event taking place."""
        if student.is_transient or event_entity not in self.EVENT_CODE_MAPPING:
            return

        progress = self.get_or_create_progress(student)

        self._update_event(
            student, progress, event_entity, event_key, direct_update=True)

        progress.updated_on = datetime.datetime.now()
        progress.put()

    def _update_event(self, student, progress, event_entity, event_key,
                      direct_update=False):
        """Updates statistics for the given event, and for derived events.

        Args:
          student: the student
          progress: the StudentProgressEntity for the student
          event_entity: the name of the affected entity (unit, lesson, etc.)
          event_key: the key for the recorded event
          direct_update: True if this event is being updated explicitly; False
              if it is being auto-updated.
        """
        if direct_update or event_entity not in self.UPDATER_MAPPING:
            if event_entity in self.UPDATER_MAPPING:
                # This is a derived event, so directly mark it as completed.
                self._set_entity_value(
                    progress, event_key, self.COMPLETED_STATE)
            else:
                # This is not a derived event, so increment its counter by one.
                self._inc(progress, event_key)
        else:
            self.UPDATER_MAPPING[event_entity](self, progress, event_key)

        if event_entity in self.DERIVED_EVENTS:
            for derived_event in self.DERIVED_EVENTS[event_entity]:
                self._update_event(
                    student=student,
                    progress=progress,
                    event_entity=derived_event['entity'],
                    event_key=derived_event['generate_parent_id'](event_key),
                )

    def get_unit_status(self, progress, unit_id):
        return self._get_entity_value(progress, self._get_unit_key(unit_id))

    def get_lesson_status(self, progress, unit_id, lesson_id):
        return self._get_entity_value(
            progress, self._get_lesson_key(unit_id, lesson_id))

    def get_activity_status(self, progress, unit_id, lesson_id):
        return self._get_entity_value(
            progress, self._get_activity_key(unit_id, lesson_id))

    def get_html_status(self, progress, unit_id, lesson_id):
        return self._get_entity_value(
            progress, self._get_html_key(unit_id, lesson_id))

    def get_block_status(self, progress, unit_id, lesson_id, block_id):
        return self._get_entity_value(
            progress, self._get_block_key(unit_id, lesson_id, block_id))

    def get_assessment_status(self, progress, assessment_id):
        return self._get_entity_value(
            progress, self._get_assessment_key(assessment_id))

    def is_block_completed(self, progress, unit_id, lesson_id, block_id):
        value = self._get_entity_value(
            progress, self._get_block_key(unit_id, lesson_id, block_id))
        return value is not None and value > 0

    def is_component_completed(self, progress, unit_id, lesson_id, cpt_id):
        value = self._get_entity_value(
            progress, self._get_component_key(unit_id, lesson_id, cpt_id))
        return value is not None and value > 0

    def is_assessment_completed(self, progress, assessment_id):
        value = self._get_entity_value(
            progress, self._get_assessment_key(assessment_id))
        return value is not None and value > 0

    @classmethod
    def get_or_create_progress(cls, student):
        progress = StudentPropertyEntity.get(student, cls.PROPERTY_KEY)
        if not progress:
            progress = StudentPropertyEntity.create(
                student=student, property_name=cls.PROPERTY_KEY)
            progress.put()
        return progress

    def get_unit_progress(self, student):
        """Returns a dict with the states of each unit."""
        if student.is_transient:
            return {}

        units = self._get_course().get_units()
        progress = self.get_or_create_progress(student)

        result = {}
        for unit in units:
            if unit.type == 'A':
                result[unit.unit_id] = self.is_assessment_completed(
                    progress, unit.unit_id)
            elif unit.type == 'U':
                value = self.get_unit_status(progress, unit.unit_id)
                result[unit.unit_id] = value or 0

        return result

    def get_lesson_progress(self, student, unit_id):
        """Returns a dict saying which lessons in this unit are completed."""
        if student.is_transient:
            return {}

        lessons = self._get_course().get_lessons(unit_id)
        progress = self.get_or_create_progress(student)

        result = {}
        for lesson in lessons:
            result[lesson.lesson_id] = {
                'html': self.get_html_status(
                    progress, unit_id, lesson.lesson_id) or 0,
                'activity': self.get_activity_status(
                    progress, unit_id, lesson.lesson_id) or 0,
            }
        return result

    def get_component_progress(self, student, unit_id, lesson_id, cpt_id):
        """Returns the progress status of the given component."""
        if student.is_transient:
            return 0

        progress = self.get_or_create_progress(student)
        return self.is_component_completed(
            progress, unit_id, lesson_id, cpt_id) or 0

    def _get_entity_value(self, progress, event_key):
        if not progress.value:
            return None
        return transforms.loads(progress.value).get(event_key)

    def _set_entity_value(self, student_property, key, value):
        """Sets the integer value of a student property.

        Note: this method does not commit the change. The calling method should
        call put() on the StudentPropertyEntity.

        Args:
          student_property: the StudentPropertyEntity
          key: the student property whose value should be incremented
          value: the value to increment this property by
        """
        try:
            progress_dict = transforms.loads(student_property.value)
        except (AttributeError, TypeError):
            progress_dict = {}

        progress_dict[key] = value
        student_property.value = transforms.dumps(progress_dict)

    def _inc(self, student_property, key, value=1):
        """Increments the integer value of a student property.

        Note: this method does not commit the change. The calling method should
        call put() on the StudentPropertyEntity.

        Args:
          student_property: the StudentPropertyEntity
          key: the student property whose value should be incremented
          value: the value to increment this property by
        """
        try:
            progress_dict = transforms.loads(student_property.value)
        except (AttributeError, TypeError):
            progress_dict = {}

        if key not in progress_dict:
            progress_dict[key] = 0

        progress_dict[key] += value
        student_property.value = transforms.dumps(progress_dict)


class ProgressStats(object):
    """Defines the course structure definition for course progress tracking."""

    def __init__(self, course):
        self._course = course
        self._tracker = UnitLessonCompletionTracker(course)

    def compute_entity_dict(self, entity, parent_ids):
        """Computes the course structure dictionary.

        Args:
            entity: str. Represents for which level of entity the dict is being
                computed. Valid entity levels are defined as keys to the dict
                defined below, COURSE_STRUCTURE_DICT.
            parent_ids: list of ids necessary to get children of the current
                entity.
        Returns:
            A nested dictionary representing the structure of the course.
            Every other level of the dictionary consists of a key, the label of
            the entity level defined by EVENT_CODE_MAPPING in
            UnitLessonCompletionTracker, whose value is a dictionary
            INSTANCES_DICT. The keys of INSTANCES_DICT are instance_ids of the
            corresponding entities, and the values are the entity_dicts of the
            instance's children, in addition to a field called 'label'. Label
            represents the user-facing name of the entity rather than
            its intrinsic id. If one of these values is empty, this means
            that the corresponding entity has no children.

            Ex:
            A Course with the following outlined structure:
                Pre Assessment
                Unit 1
                    Lesson 1
                Unit 2

            will have the following dictionary representation:
                {
                    's': {
                        1: {
                            'label': 'Pre Assessment'
                        }
                    },
                    'u': {
                        2: {
                            'l': {
                                3: {
                                    'label': 1
                                }
                            },
                            'label': 1
                        },
                        4: {
                            'label': 2
                        }
                    }
                    'label': 'UNTITLED COURSE'
                }
        """
        entity_dict = {'label': self._get_label(entity, parent_ids)}
        for child_entity, get_children_ids in self.COURSE_STRUCTURE_DICT[
                entity]['children']:
            child_entity_dict = {}
            for child_id in get_children_ids(self, *parent_ids):
                new_parent_ids = parent_ids + [child_id]
                child_entity_dict[child_id] = self.compute_entity_dict(
                    child_entity, new_parent_ids)
            entity_dict[UnitLessonCompletionTracker.EVENT_CODE_MAPPING[
                child_entity]] = child_entity_dict
        return entity_dict

    def _get_course(self):
        return self._course

    def _get_unit_ids_of_type_unit(self):
        units = self._get_course().get_units_of_type(verify.UNIT_TYPE_UNIT)
        return [unit.unit_id for unit in units]

    def _get_assessment_ids(self):
        assessments = self._get_course().get_assessment_list()
        return [a.unit_id for a in assessments]

    def _get_lesson_ids(self, unit_id):
        lessons = self._get_course().get_lessons(unit_id)
        return [lesson.lesson_id for lesson in lessons]

    def _get_activity_ids(self, unit_id, lesson_id):
        unit = self._get_course().find_unit_by_id(unit_id)
        if self._get_course().find_lesson_by_id(unit, lesson_id).activity:
            return [0]
        return []

    def _get_html_ids(self, unused_unit_id, unused_lesson_id):
        return [0]

    def _get_block_ids(self, unit_id, lesson_id, unused_activity_id):
        return self._tracker.get_valid_block_ids(unit_id, lesson_id)

    def _get_component_ids(self, unit_id, lesson_id, unused_html_id):
        return self._tracker.get_valid_component_ids(unit_id, lesson_id)

    def _get_label(self, entity, parent_ids):
        return self.ENTITY_TO_HUMAN_READABLE_NAME_DICT[entity](
            self, *parent_ids)

    def _get_course_label(self):
        # pylint: disable-msg=protected-access
        return courses.Course.get_environ(self._get_course().app_context)[
            'course']['title']

    def _get_unit_label(self, unit_id):
        unit = self._get_course().find_unit_by_id(unit_id)
        return 'Unit %s' % unit.index

    def _get_assessment_label(self, unit_id):
        assessment = self._get_course().find_unit_by_id(unit_id)
        return assessment.title

    def _get_lesson_label(self, unit_id, lesson_id):
        unit = self._get_course().find_unit_by_id(unit_id)
        lesson = self._get_course().find_lesson_by_id(unit, lesson_id)
        return lesson.index

    def _get_activity_label(self, unit_id, lesson_id, unused_activity_id):
        return str('L%s.%s' % (
            self._get_course().find_unit_by_id(unit_id).index,
            self._get_lesson_label(unit_id, lesson_id)))

    def _get_html_label(self, unit_id, lesson_id, unused_html_id):
        return self._get_activity_label(unit_id, lesson_id, unused_html_id)

    def _get_block_label(self, unit_id, lesson_id, unused_activity_id,
                         block_id):
        return str('L%s.%s.%s' % (
            self._get_course().find_unit_by_id(unit_id).index,
            self._get_lesson_label(unit_id, lesson_id),
            block_id))

    def _get_component_label(self, unit_id, lesson_id, unused_html_id,
                             component_id):
        return self._get_block_label(
            unit_id, lesson_id, unused_html_id, component_id)

    # Outlines the structure of the course. The key is the entity level, and
    # its value is a dictionary with following keys and its values:
    #   'children': list of tuples. Each tuple consists of string representation
    #               of the child entity(ex: 'lesson') and a function to get the
    #               children elements. If the entity does not have children, the
    #               value will be an empty list.
    #   'id': instance_id of the entity. If the entity is represented by a class
    #         with an id attribute(ex: units), string representation of the
    #         attribute is stored here. If the entity is defined by a dictionary
    #         (ex: components), then the value is the string 'None'.
    #
    COURSE_STRUCTURE_DICT = {
        'course': {
            'children': [('unit', _get_unit_ids_of_type_unit),
                         ('assessment', _get_assessment_ids)],
        },
        'unit': {
            'children': [('lesson', _get_lesson_ids)],
        },
        'assessment': {
            'children': [],
        },
        'lesson': {
            'children': [('activity', _get_activity_ids),
                         ('html', _get_html_ids)],
        },
        'activity': {
            'children': [('block', _get_block_ids)],
        },
        'html': {
            'children': [('component', _get_component_ids)],
        },
        'block': {
            'children': [],
        },
        'component': {
            'children': [],
        }
    }

    ENTITY_TO_HUMAN_READABLE_NAME_DICT = {
        'course': _get_course_label,
        'unit': _get_unit_label,
        'assessment': _get_assessment_label,
        'lesson': _get_lesson_label,
        'activity': _get_activity_label,
        'html': _get_html_label,
        'block': _get_block_label,
        'component': _get_component_label
    }
