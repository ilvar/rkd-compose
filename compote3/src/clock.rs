//! Just enough calendar arithmetic to build GitHub's `pushed:>YYYY-MM-DD`
//! search qualifier without taking on a date-time dependency.

use std::time::SystemTime;
use std::time::UNIX_EPOCH;

/// A proleptic Gregorian date, in UTC.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Date {
    pub year: i64,
    pub month: i64,
    pub day: i64,
}

impl Date {
    /// `YYYY-MM-DD`, the only format GitHub search accepts for a date bound.
    pub fn to_iso_date(self) -> String {
        let Date { year, month, day } = self;
        format!("{year:04}-{month:02}-{day:02}")
    }
}

/// Whole days elapsed since 1970-01-01, or `None` for a clock set before the
/// epoch or beyond `i64` seconds.
pub fn days_since_epoch(now: SystemTime) -> Option<i64> {
    let seconds = now.duration_since(UNIX_EPOCH).ok()?.as_secs();
    let seconds = i64::try_from(seconds).ok()?;
    Some(seconds.div_euclid(86_400))
}

/// The UTC date `days` before `now`.
pub fn date_days_before(now: SystemTime, days: i64) -> Option<Date> {
    let today = days_since_epoch(now)?;
    Some(civil_from_days(today.checked_sub(days)?))
}

/// Howard Hinnant's `civil_from_days`: days since the epoch to a civil date.
pub fn civil_from_days(days: i64) -> Date {
    // Shift the era so it starts on 0000-03-01, which moves the leap day to the
    // end of the year and makes every 400-year era exactly 146_097 days long.
    let shifted = days + 719_468;
    let era = shifted.div_euclid(146_097);
    let day_of_era = shifted - era * 146_097;
    let year_of_era =
        (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_prime = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_prime + 2) / 5 + 1;
    let month = if month_prime < 10 {
        month_prime + 3
    } else {
        month_prime - 9
    };
    let year = year_of_era + era * 400 + i64::from(month <= 2);

    Date { year, month, day }
}

/// The inverse of [`civil_from_days`], so a date can be turned back into the
/// number the calendar arithmetic runs on.
pub fn days_from_civil(date: Date) -> i64 {
    let Date { year, month, day } = date;
    // Same March-based era trick as `civil_from_days`, run backwards.
    let year = year - i64::from(month <= 2);
    let era = year.div_euclid(400);
    let year_of_era = year - era * 400;
    let month_prime = if month > 2 { month - 3 } else { month + 9 };
    let day_of_year = (153 * month_prime + 2) / 5 + day - 1;
    let day_of_era = year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;

    era * 146_097 + day_of_era - 719_468
}

#[cfg(test)]
mod tests {
    use super::civil_from_days;
    use super::date_days_before;
    use super::Date;
    use std::time::Duration;
    use std::time::UNIX_EPOCH;

    #[test]
    fn the_epoch_is_1970_01_01() {
        assert_eq!(
            civil_from_days(0),
            Date {
                year: 1970,
                month: 1,
                day: 1
            }
        );
    }

    #[test]
    fn known_dates_round_trip() {
        assert_eq!(civil_from_days(-1).to_iso_date(), "1969-12-31");
        assert_eq!(civil_from_days(19_723).to_iso_date(), "2024-01-01");
        assert_eq!(civil_from_days(19_782).to_iso_date(), "2024-02-29");
        assert_eq!(civil_from_days(20_322).to_iso_date(), "2025-08-22");
    }

    #[test]
    fn subtracting_days_crosses_a_month_boundary() {
        let leap_day = UNIX_EPOCH + Duration::from_secs(19_782 * 86_400 + 3_600);
        let yesterday = date_days_before(leap_day, 1).expect("in range");

        assert_eq!(yesterday.to_iso_date(), "2024-02-28");
    }

    #[test]
    fn a_week_before_the_epoch_is_representable() {
        let week_ago = date_days_before(UNIX_EPOCH, 7).expect("in range");
        assert_eq!(week_ago.to_iso_date(), "1969-12-25");
    }
}
