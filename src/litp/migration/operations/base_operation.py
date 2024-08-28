

class BaseOperation(object):
    """
    Base type for all migration operations.
    """

    def mutate_forward(self, model_manager):
        """
        All subclasses of the BaseOperation class must implement \
            mutate_forward in order to define the logic to migrate the model \
            from one state to another.

        :param model_manager: The model manager to perform migration on.
        :type  model_manager: litp.core.model_manager.ModelManager

        """

        raise NotImplementedError(
            'subclasses of BaseOperation must provide a '
            'mutate_forward() method'
        )

    def mutate_backward(self, model_manager):
        """
        All subclasses of the BaseOperation class must implement \
            mutate_backward in order to restore the model after a \
            previous migration.

        :param model_manager: The model manager to perform migration on.
        :type  model_manager: litp.core.model_manager.ModelManager

        """

        raise NotImplementedError(
            'subclasses of BaseOperation must provide a '
            'mutate_backward() method'
        )
