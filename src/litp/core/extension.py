##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

# The following import allows other projects to import ViewError from
# this module as they used to do before it was moved to litp.core.exceptions
from litp.core.exceptions import ViewError  # pylint: disable=W0611


class ModelExtension(object):
    '''Base class for LITP Model Extensions'''

    def define_item_types(self):
        '''Registers Item Types with the Deployment Manager

        :returns: A list of :class:`litp.core.model_type.ItemType` objects
        :rtype: list
        '''
        return []

    def define_property_types(self):
        '''Registers Property Types with the Deployment Manager

        :returns: A list of :class:`litp.core.model_type.PropertyType` objects
        :rtype: list
        '''
        return []
