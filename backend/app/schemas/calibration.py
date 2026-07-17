"""Public Phase 2 calibration profile and marker-analysis schemas."""

from base64 import b64decode
from binascii import Error as BinasciiError
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from backend.app.calibration_contracts import (
    APPROVED_ARUCO_DICTIONARIES,
    CORNER_LABEL_ORDER,
    MARKER_BORDER_BITS,
    MARKER_ID_MAX,
    MARKER_ID_MIN,
    MAX_PREVIEW_BYTES,
    MAX_PREVIEW_EDGE_PX,
    MAX_RECTIFIED_EDGE_PX,
    ArucoDictionary,
    CornerLabel,
)

ProfileName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]
MarkerSize = Annotated[float, Field(ge=10.0, le=300.0, allow_inf_nan=False)]
PerspectiveRatio = Annotated[float, Field(ge=1.0, le=10.0, allow_inf_nan=False)]
HomographyCondition = Annotated[
    float,
    Field(ge=10.0, le=1_000_000_000_000.0, allow_inf_nan=False),
]
EdgeResidual = Annotated[float, Field(ge=0.1, le=20.0, allow_inf_nan=False)]
RectifiedScale = Annotated[float, Field(ge=1.0, le=6.0, allow_inf_nan=False)]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NonNegativeFiniteFloat = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]


class CalibrationProfileCreateRequest(BaseModel):
    """Exactly the user-configurable fields of an immutable profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: ProfileName
    dictionary: ArucoDictionary
    marker_id: int = Field(ge=MARKER_ID_MIN, le=MARKER_ID_MAX)
    marker_size_mm: MarkerSize
    minimum_marker_side_px: int = Field(ge=24, le=4096)
    maximum_perspective_ratio: PerspectiveRatio
    maximum_homography_condition_number: HomographyCondition
    maximum_marker_edge_residual_px: EdgeResidual
    rectified_pixels_per_mm: RectifiedScale


class CalibrationProfileResponse(BaseModel):
    """Complete safe persisted profile representation."""

    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    id: str
    name: ProfileName
    dictionary: ArucoDictionary
    marker_id: int = Field(ge=MARKER_ID_MIN, le=MARKER_ID_MAX)
    marker_size_mm: MarkerSize
    border_bits: Literal[1]
    minimum_marker_side_px: int = Field(ge=24, le=4096)
    maximum_perspective_ratio: PerspectiveRatio
    maximum_homography_condition_number: HomographyCondition
    maximum_marker_edge_residual_px: EdgeResidual
    rectified_pixels_per_mm: RectifiedScale
    is_active: bool
    created_at: datetime
    activated_at: datetime | None

    @field_validator("id", mode="after")
    @classmethod
    def id_must_be_uuid(cls, value: str) -> str:
        UUID(value)
        return value

    @field_validator("created_at", "activated_at", mode="after")
    @classmethod
    def normalize_timestamp_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None or value.tzinfo is not None:
            return value
        return value.replace(tzinfo=UTC)


class CalibrationProfileListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[CalibrationProfileResponse]
    total: int = Field(ge=0)


class CalibrationDefaultsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dictionary: ArucoDictionary = ArucoDictionary.DICT_4X4_50
    marker_id: Annotated[int, Field(ge=MARKER_ID_MIN, le=MARKER_ID_MAX)] = 0
    marker_size_mm: MarkerSize = 100.0
    minimum_marker_side_px: Annotated[int, Field(ge=24, le=4096)] = 64
    maximum_perspective_ratio: PerspectiveRatio = 3.0
    maximum_homography_condition_number: HomographyCondition = 1_000_000.0
    maximum_marker_edge_residual_px: EdgeResidual = 2.0
    rectified_pixels_per_mm: RectifiedScale = 4.0


class CalibrationOptionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dictionaries: list[ArucoDictionary]
    marker_id_min: int
    marker_id_max: int
    border_bits: int
    defaults: CalibrationDefaultsResponse

    @model_validator(mode="after")
    def values_must_match_frozen_options(self) -> "CalibrationOptionsResponse":
        if tuple(self.dictionaries) != APPROVED_ARUCO_DICTIONARIES:
            raise ValueError("dictionaries must match the approved order")
        if (
            self.marker_id_min != MARKER_ID_MIN
            or self.marker_id_max != MARKER_ID_MAX
            or self.border_bits != MARKER_BORDER_BITS
        ):
            raise ValueError("marker limits must match the frozen contract")
        return self


def calibration_options() -> CalibrationOptionsResponse:
    """Return the frozen, database-independent Phase 2 option set."""

    return CalibrationOptionsResponse(
        dictionaries=list(APPROVED_ARUCO_DICTIONARIES),
        marker_id_min=MARKER_ID_MIN,
        marker_id_max=MARKER_ID_MAX,
        border_bits=MARKER_BORDER_BITS,
        defaults=CalibrationDefaultsResponse(),
    )


class OrderedCornerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    label: CornerLabel
    x_px: FiniteFloat
    y_px: FiniteFloat


class EdgeValuesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    top: NonNegativeFiniteFloat
    right: NonNegativeFiniteFloat
    bottom: NonNegativeFiniteFloat
    left: NonNegativeFiniteFloat


class MarkerEdgeQualityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    metric_name: Literal["marker_edge_localization_residual"]
    description: Literal["Sampled marker-border localization residual in image pixels."]
    rms_px: NonNegativeFiniteFloat
    maximum_px: NonNegativeFiniteFloat
    sample_count: int = Field(gt=0)
    per_edge_rms_px: EdgeValuesResponse
    threshold_px: EdgeResidual
    valid: Literal[True]

    @model_validator(mode="after")
    def maximum_must_cover_rms(self) -> "MarkerEdgeQualityResponse":
        if self.maximum_px < self.rms_px:
            raise ValueError("maximum_px must not be below rms_px")
        return self


class PreviewImageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    media_type: Literal["image/png"]
    width_px: int = Field(ge=1, le=MAX_RECTIFIED_EDGE_PX)
    height_px: int = Field(ge=1, le=MAX_RECTIFIED_EDGE_PX)
    data_base64: str = Field(min_length=1)

    @field_validator("data_base64", mode="after")
    @classmethod
    def validate_bounded_png(cls, value: str) -> str:
        try:
            decoded = b64decode(value, validate=True)
        except (ValueError, BinasciiError) as error:
            raise ValueError("preview must contain valid base64") from error
        if len(decoded) > MAX_PREVIEW_BYTES:
            raise ValueError("preview exceeds the public byte limit")
        if not decoded.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("preview must contain PNG bytes")
        return value


MatrixRow = tuple[FiniteFloat, FiniteFloat, FiniteFloat]
Matrix3x3Response = tuple[MatrixRow, MatrixRow, MatrixRow]


class CalibrationTestResponse(BaseModel):
    """Complete marker-only evidence returned by a successful calibration test."""

    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    profile_id: str
    dictionary: ArucoDictionary
    marker_id: int = Field(ge=MARKER_ID_MIN, le=MARKER_ID_MAX)
    marker_size_mm: MarkerSize
    ordered_corners: tuple[
        OrderedCornerResponse,
        OrderedCornerResponse,
        OrderedCornerResponse,
        OrderedCornerResponse,
    ]
    orientation_degrees: Annotated[
        float,
        Field(ge=-180.0, lt=180.0, allow_inf_nan=False),
    ]
    edge_lengths_px: EdgeValuesResponse
    perspective_ratio: PerspectiveRatio
    image_to_marker_mm: Matrix3x3Response
    marker_mm_to_image: Matrix3x3Response
    homography_condition_number: Annotated[
        float,
        Field(ge=1.0, allow_inf_nan=False),
    ]
    rectified_width_px: int = Field(ge=1, le=MAX_RECTIFIED_EDGE_PX)
    rectified_height_px: int = Field(ge=1, le=MAX_RECTIFIED_EDGE_PX)
    rectified_pixels_per_mm: RectifiedScale
    marker_edge_quality: MarkerEdgeQualityResponse
    annotated_preview: PreviewImageResponse
    rectified_preview: PreviewImageResponse

    @field_validator("profile_id", mode="after")
    @classmethod
    def profile_id_must_be_uuid(cls, value: str) -> str:
        UUID(value)
        return value

    @field_validator("ordered_corners", mode="after")
    @classmethod
    def corners_must_use_canonical_order(
        cls,
        value: tuple[
            OrderedCornerResponse,
            OrderedCornerResponse,
            OrderedCornerResponse,
            OrderedCornerResponse,
        ],
    ) -> tuple[
        OrderedCornerResponse,
        OrderedCornerResponse,
        OrderedCornerResponse,
        OrderedCornerResponse,
    ]:
        if tuple(corner.label for corner in value) != CORNER_LABEL_ORDER:
            raise ValueError("ordered_corners must use canonical marker order")
        return value

    @model_validator(mode="after")
    def previews_must_match_their_role_and_rectified_geometry(
        self,
    ) -> "CalibrationTestResponse":
        if (
            self.annotated_preview.width_px > MAX_PREVIEW_EDGE_PX
            or self.annotated_preview.height_px > MAX_PREVIEW_EDGE_PX
        ):
            raise ValueError("annotated preview exceeds its edge limit")
        if (
            self.rectified_preview.width_px != self.rectified_width_px
            or self.rectified_preview.height_px != self.rectified_height_px
        ):
            raise ValueError("rectified preview dimensions do not match geometry")
        return self

