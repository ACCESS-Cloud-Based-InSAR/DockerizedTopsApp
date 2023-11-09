from typing import List

from pydantic import BaseModel


class topsappParams(BaseModel):
    reference_scenes: List[str]
    secondary_scenes: List[str]
    frame_id: int
    estimate_ionosphere_delay: bool = True
    compute_solid_earth_tide: bool = True
    output_resolution: int = 90
    unfiltered_coherence: bool = True
    goldstein_filter_power: float = .5
    dense_offsets: bool = False
    wrapped_phase_layer: bool = False
    esd_coherence_threshold: float = -1

    def is_standard_gunw_product(self) -> bool:
        """Version 3+"""
        checks = [
            self.estimate_ionosphere_delay,
            self.frame_id != -1,
            self.compute_solid_earth_tide,
            not self.dense_offsets,
            self.unfiltered_coherence,
            self.esd_coherence_threshold == -1,
            not self.wrapped_phase_layer,
            self.goldstein_filter_power == .5,
            self.output_resolution == 90,
        ]
        return all(checks)
