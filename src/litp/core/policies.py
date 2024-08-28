class LockPolicy(object):

    CREATE_LOCKS = 'create_locks'
    NO_LOCKS = 'no_locks'
    INITIAL_LOCKS = 'initial_locks'

    def __init__(self, action=CREATE_LOCKS, lock_tasks_list=None):

        self.action = action
        self.lock_tasks_list = lock_tasks_list

    def getClusters(self):
        return self.lock_tasks_list

    def getAction(self):
        return self.action
