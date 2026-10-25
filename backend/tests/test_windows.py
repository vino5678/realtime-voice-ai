import numpy as np
import pytest

from app.audio.windows import iter_audio_windows, stitch_crossfaded


def test_audio_windows_preserve_coverage_and_overlap():
    samples = np.arange(23, dtype=np.float32)
    windows = list(iter_audio_windows(samples, sample_rate=1, window_seconds=5, overlap_seconds=1))

    assert [(w.start_sample, w.end_sample) for w in windows] == [
        (0, 5),
        (4, 9),
        (8, 13),
        (12, 17),
        (16, 21),
        (20, 23),
    ]
    assert np.array_equal(windows[0].samples, samples[:5])
    assert np.array_equal(windows[-1].samples, samples[20:])


def test_audio_windows_omit_tail_already_covered_by_overlap():
    samples = np.arange(22, dtype=np.float32)
    windows = list(iter_audio_windows(samples, sample_rate=1, window_seconds=2, overlap_seconds=1))

    assert windows[-1].end_sample == len(samples)
    assert windows[-1].start_sample == 20
    assert len(windows) == 21


def test_crossfade_stitch_reconstructs_expected_duration_and_smooth_join():
    first = np.zeros(8, dtype=np.float32)
    second = np.ones(8, dtype=np.float32)

    result = stitch_crossfaded([first, second], overlap_samples=4)

    assert len(result) == 12
    assert np.allclose(result[4:8], np.linspace(0, 1, 4, dtype=np.float32))
    assert abs(result[8] - result[7]) < 1


def test_stitch_without_overlap_concatenates():
    result = stitch_crossfaded(
        [np.array([1, 2], dtype=np.float32), np.array([3], dtype=np.float32)],
        overlap_samples=0,
    )
    assert np.array_equal(result, np.array([1, 2, 3], dtype=np.float32))


@pytest.mark.parametrize(
    ("window_seconds", "overlap_seconds"),
    [(0, 0), (1, -1), (1, 1)],
)
def test_audio_window_rejects_invalid_durations(window_seconds, overlap_seconds):
    with pytest.raises(ValueError):
        list(iter_audio_windows(np.zeros(4, dtype=np.float32), 4, window_seconds, overlap_seconds))


def test_crossfade_rejects_incomplete_overlap():
    with pytest.raises(ValueError):
        stitch_crossfaded([np.zeros(2, dtype=np.float32), np.zeros(1, dtype=np.float32)], 2)
