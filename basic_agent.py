# -*- coding: utf-8 -*-
"""BasicAgent: the original competition entry; train / test unchanged, delegating to the YiXiao clinical runtime."""
import json
import sys

from my_doctor_agent import MyDoctorAgent, _parse_args


class BasicAgent:
    def __init__(self, fake=False):
        self._doctor = MyDoctorAgent(fake=fake)

    def train(self, data=None):
        return self._doctor.train()

    def test(self, case_input):
        return self._doctor.test(case_input)


def main():
    args = _parse_args()
    agent = BasicAgent(fake=args.fake)
    if args.mode == 'train':
        print(json.dumps(agent.train(), ensure_ascii=False, indent=2))
        return
    result = agent.test({'chief_complaint': args.complaint, 'age': args.age, 'sex': args.sex,
                         'duration': args.duration, 'symptoms': [s for s in args.symptoms.split(',') if s],
                         'past_history': args.history, 'allergies': args.allergies,
                         'medications': args.medications})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
