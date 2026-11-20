class CreateMetadataError(Exception):
    pass


class VideoAlreadyUploadedError(Exception):
    pass


class NoUploadedRecordError(Exception):
    pass


class MissingThumbnailDataError(Exception):
    pass


class ThumbnailSelectionError(Exception):
    pass


class QuotaExceededError(Exception):
    pass


class AuthRequiredError(Exception):
    pass
