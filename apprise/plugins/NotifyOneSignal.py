# -*- coding: utf-8 -*-
#
# Copyright (C) 2020 Chris Caron <lead2gold@gmail.com>
# All rights reserved.
#
# This code is licensed under the MIT License.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files(the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and / or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions :
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

# One Signal requires that you've signed up with the service and
# generated yourself an API Key and APP ID.

# Sources:
#  - https://documentation.onesignal.com/docs/accounts-and-keys
#  - https://documentation.onesignal.com/reference/create-notification

import requests
from json import dumps
from itertools import chain

from .NotifyBase import NotifyBase
from ..common import NotifyType
from ..common import NotifyImageSize
from ..utils import validate_regex
from ..utils import parse_list
from ..utils import parse_bool
from ..utils import is_email
from ..AppriseLocale import gettext_lazy as _


class OneSignalCategory(NotifyBase):
    """
    We define the different category types that we can notify via OneSignal
    """
    PLAYER = 'include_player_ids'
    EMAIL = 'include_email_tokens'
    USER = 'include_external_user_ids'
    SEGMENT = 'included_segments'


ONESIGNAL_CATEGORIES = (
    OneSignalCategory.PLAYER,
    OneSignalCategory.EMAIL,
    OneSignalCategory.USER,
    OneSignalCategory.SEGMENT,
)


class NotifyOneSignal(NotifyBase):
    """
    A wrapper for OneSignal Notifications
    """
    # The default descriptive name associated with the Notification
    service_name = 'OneSignal'

    # The services URL
    service_url = 'https://onesignal.com'

    # The default protocol
    secure_protocol = 'onesignal'

    # A URL that takes you to the setup/help of the specific protocol
    setup_url = 'https://github.com/caronc/apprise/wiki/Notify_onesignal'

    # Notification
    notify_url = "https://onesignal.com/api/v1/notifications"

    # Allows the user to specify the NotifyImageSize object
    image_size = NotifyImageSize.XY_72

    # The maximum allowable batch sizes per message
    maximum_batch_size = 2000

    # Define object templates
    templates = (
        '{schema}://{app}@{apikey}/{targets}',
        '{schema}://{template}:{app}@{apikey}/{targets}',
    )

    # Define our template
    template_tokens = dict(NotifyBase.template_tokens, **{
        # The App_ID is a UUID
        # such as: 8250eaf6-1a58-489e-b136-7c74a864b434
        'app': {
            'name': _('App ID'),
            'type': 'string',
            'private': True,
            'required': True,
        },
        'template': {
            'name': _('Template'),
            'type': 'string',
            'private': True,
        },
        'apikey': {
            'name': _('API Key'),
            'type': 'string',
            'private': True,
            'required': True,
        },
        'target_device': {
            'name': _('Target Player ID'),
            'type': 'string',
            'map_to': 'targets',
        },
        'target_email': {
            'name': _('Target Email'),
            'type': 'string',
            'map_to': 'targets',
        },
        'target_user': {
            'name': _('Target User'),
            'type': 'string',
            'prefix': '@',
            'map_to': 'targets',
        },
        'target_segment': {
            'name': _('Include Segment'),
            'type': 'string',
            'prefix': '#',
            'map_to': 'targets',
        },
        'targets': {
            'name': _('Targets'),
            'type': 'list:string',
        },
    })

    template_args = dict(NotifyBase.template_args, **{
        'to': {
            'alias_of': 'targets',
        },
        'image': {
            'name': _('Include Image'),
            'type': 'bool',
            'default': True,
            'map_to': 'include_image',
        },
        'batch': {
            'name': _('Batch Mode'),
            'type': 'bool',
            'default': False,
        },
        'template': {
            'alias_of': 'template',
        },
        'subtitle': {
            'name': _('Subtitle'),
            'type': 'string',
        },
        'language': {
            'name': _('Language'),
            'type': 'string',
            'default': 'en',
        },
    })

    def __init__(self, app, apikey, targets=None, include_image=True,
                 template=None, subtitle=None, language=None, batch=False,
                 **kwargs):
        """
        Initialize OneSignal

        """
        super(NotifyOneSignal, self).__init__(**kwargs)

        # The apikey associated with the account
        self.apikey = validate_regex(apikey)
        if not self.apikey:
            msg = 'An invalid OneSignal API key ' \
                  '({}) was specified.'.format(apikey)
            self.logger.warning(msg)
            raise TypeError(msg)

        # The App ID associated with the account
        self.app = validate_regex(app)
        if not self.app:
            msg = 'An invalid OneSignal Application ID ' \
                  '({}) was specified.'.format(app)
            self.logger.warning(msg)
            raise TypeError(msg)

        # Prepare Batch Mode Flag
        self.batch_size = self.maximum_batch_size if batch else 1

        # Place a thumbnail image inline with the message body
        self.include_image = include_image

        # Our Assorted Types of Targets
        self.targets = {
            OneSignalCategory.PLAYER: [],
            OneSignalCategory.EMAIL: [],
            OneSignalCategory.USER: [],
            OneSignalCategory.SEGMENT: [],
        }

        # Assign our template (if defined)
        self.template_id = template

        # Assign our subtitle (if defined)
        self.subtitle = subtitle

        # Our Language
        self.language = language.strip().lower()[0:2]\
            if language \
            else NotifyOneSignal.template_args['language']['default']

        if not self.language or len(self.language) != 2:
            msg = 'An invalid OneSignal Language ({}) was specified.'.format(
                language)
            self.logger.warning(msg)
            raise TypeError(msg)

        # Sort our targets
        for _target in parse_list(targets):
            target = _target.strip()
            if len(target) < 2:
                self.logger.debug('Ignoring OneSignal Entry: %s' % target)
                continue

            if target.startswith(
                    NotifyOneSignal.template_tokens
                    ['target_user']['prefix']):

                self.targets[OneSignalCategory.USER].append(target)
                self.logger.debug(
                    'Detected OneSignal UserID: %s' %
                    self.targets[OneSignalCategory.USER][-1])
                continue

            if target.startswith(
                    NotifyOneSignal.template_tokens
                    ['target_segment']['prefix']):

                self.targets[OneSignalCategory.SEGMENT].append(target)
                self.logger.debug(
                    'Detected OneSignal Include Segment: %s' %
                    self.targets[OneSignalCategory.SEGMENT][-1])
                continue

            result = is_email(target)
            if result:
                self.targets[OneSignalCategory.EMAIL]\
                    .append(result['full_email'])
                self.logger.debug(
                    'Detected OneSignal Email: %s' %
                    self.targets[OneSignalCategory.EMAIL][-1])

            else:
                # Add element as Player ID
                self.targets[OneSignalCategory.PLAYER].append(target)
                self.logger.debug(
                    'Detected OneSignal Player ID: %s' %
                    self.targets[OneSignalCategory.PLAYER][-1])

        return

    def send(self, body, title='', notify_type=NotifyType.INFO, **kwargs):
        """
        Perform OneSignal Notification
        """

        headers = {
            'User-Agent': self.app_id,
            'Content-Type': 'application/json; charset=utf-8',
            "Authorization": "Basic {}".format(self.apikey),
        }

        has_error = False
        sent_count = 0

        payload = {
            'app_id': self.app,

            'headings': {
                self.language: title if title else self.app_desc,
            },
            'contents': {
                self.language: body,
            },

            # Sending true wakes your app from background to run custom native
            # code (Apple interprets this as content-available=1).
            # Note: Not applicable if the app is in the "force-quit" state
            #      (i.e app was swiped away). Omit the contents field to
            #      prevent displaying a visible notification.
            'content_available': True,
        }

        if self.subtitle:
            payload.update({
                'subtitle': {
                    self.language: self.subtitle,
                },
            })

        if self.template_id:
            payload['template_id'] = self.template_id

        # Acquire our large_icon image URL (if set)
        image_url = None if not self.include_image \
            else self.image_url(notify_type)
        if image_url:
            payload['large_icon'] = image_url

        # Acquire our small_icon image URL (if set)
        image_url = None if not self.include_image \
            else self.image_url(notify_type, image_size=NotifyImageSize.XY_32)
        if image_url:
            payload['small_icon'] = image_url

        for category in ONESIGNAL_CATEGORIES:
            # Create a pointer to our list of targets for specified category
            targets = self.targets[category]
            for index in range(0, len(targets), self.batch_size):
                payload[category] = targets[index:index + self.batch_size]

                # Track our sent count
                sent_count += len(payload[category])

                self.logger.debug('OneSignal POST URL: %s (cert_verify=%r)' % (
                    self.notify_url, self.verify_certificate,
                ))
                self.logger.debug('OneSignal Payload: %s' % str(payload))

                # Always call throttle before any remote server i/o is made
                self.throttle()
                try:
                    r = requests.post(
                        self.notify_url,
                        data=dumps(payload),
                        headers=headers,
                        verify=self.verify_certificate,
                        timeout=self.request_timeout,
                    )
                    if r.status_code not in (
                            requests.codes.ok, requests.codes.no_content):
                        # We had a problem
                        status_str = \
                            NotifyOneSignal.http_response_code_lookup(
                                r.status_code)

                        self.logger.warning(
                            'Failed to send OneSignal notification: '
                            '{}{}error={}.'.format(
                                status_str,
                                ', ' if status_str else '',
                                r.status_code))

                        self.logger.debug(
                            'Response Details:\r\n%s', r.content)

                        has_error = True

                    else:
                        self.logger.info('Sent OneSignal notification.')

                except requests.RequestException as e:
                    self.logger.warning(
                        'A Connection error occurred sending OneSignal '
                        'notification.'
                    )
                    self.logger.debug('Socket Exception: %s', str(e))

                    has_error = True

        if not sent_count:
            # There is no one to notify; we need to capture this and not
            # return a valid
            self.logger.warning('There are no OneSignal targets to notify')
            return False

        return not has_error

    def url(self, privacy=False, *args, **kwargs):
        """
        Returns the URL built dynamically based on specified arguments.
        """

        # Define any URL parameters
        params = {
            'image': 'yes' if self.include_image else 'no',
        }

        # Extend our parameters
        params.update(self.url_parameters(privacy=privacy, *args, **kwargs))

        return '{schema}://{tp_id}{app}@{apikey}/{targets}?{params}'.format(
            schema=self.secure_protocol,
            tp_id='{}:'.format(
                self.pprint(self.template_id, privacy, safe=''))
            if self.template_id else '',
            app=self.pprint(self.app, privacy, safe=''),
            apikey=self.pprint(self.apikey, privacy, safe=''),
            targets='/'.join(chain(
                [NotifyOneSignal.quote(x)
                    for x in self.targets[OneSignalCategory.PLAYER]],
                [NotifyOneSignal.quote(x)
                    for x in self.targets[OneSignalCategory.EMAIL]],
                [NotifyOneSignal.quote('{}{}'.format(
                    NotifyOneSignal.template_tokens
                    ['target_user']['prefix'], x), safe='')
                    for x in self.targets[OneSignalCategory.USER]],
                [NotifyOneSignal.quote('{}{}'.format(
                    NotifyOneSignal.template_tokens
                    ['target_segment']['prefix'], x), safe='')
                    for x in self.targets[OneSignalCategory.SEGMENT]])),
            params=NotifyOneSignal.urlencode(params),
        )

    @staticmethod
    def parse_url(url):
        """
        Parses the URL and returns enough arguments that can allow
        us to re-instantiate this object.

        """
        results = NotifyBase.parse_url(url, verify_host=False)
        if not results:
            # We're done early as we couldn't load the results
            return results

        if not results.get('password'):
            # The APP ID identifier associated with the account
            results['app'] = NotifyOneSignal.unquote(results['user'])

        else:
            # The APP ID identifier associated with the account
            results['app'] = NotifyOneSignal.unquote(results['password'])
            # The Template ID
            results['template'] = NotifyOneSignal.unquote(results['user'])

        # Get Image Boolean (if set)
        results['include_image'] = \
            parse_bool(
                results['qsd'].get(
                    'image',
                    NotifyOneSignal.template_args['image']['default']))

        # The API Key is stored in the hostname
        results['apikey'] = NotifyOneSignal.unquote(results['host'])

        # Get our Device IDs
        results['targets'] = NotifyOneSignal.split_path(results['fullpath'])

        # The 'to' makes it easier to use yaml configuration
        if 'to' in results['qsd'] and len(results['qsd']['to']):
            results['targets'] += \
                NotifyOneSignal.parse_list(results['qsd']['to'])

        if 'app' in results['qsd'] and len(results['qsd']['app']):
            results['app'] = \
                NotifyOneSignal.unquote(results['qsd']['app'])

        if 'apikey' in results['qsd'] and len(results['qsd']['apikey']):
            results['apikey'] = \
                NotifyOneSignal.unquote(results['qsd']['apikey'])

        if 'template' in results['qsd'] and len(results['qsd']['template']):
            results['template'] = \
                NotifyOneSignal.unquote(results['qsd']['template'])

        if 'subtitle' in results['qsd'] and len(results['qsd']['subtitle']):
            results['subtitle'] = \
                NotifyOneSignal.unquote(results['qsd']['subtitle'])

        if 'lang' in results['qsd'] and len(results['qsd']['lang']):
            results['language'] = \
                NotifyOneSignal.unquote(results['qsd']['lang'])

        return results