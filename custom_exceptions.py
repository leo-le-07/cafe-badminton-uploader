class VideoAlreadyUploadedError(Exception):
    pass


class NoUploadedRecordError(Exception):
    pass


class MissingThumbnailDataError(Exception):
    pass


class QuotaExceededError(Exception):
    pass


class AuthRequiredError(Exception):
    pass


class CorruptUploadRecordError(ValueError):
    """upload.json exists but cannot be read: whether the video is already on
    YouTube is unknown, so nothing may upload or delete the workspace."""
