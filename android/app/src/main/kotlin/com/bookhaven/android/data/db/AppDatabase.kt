package com.bookhaven.android.data.db

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.bookhaven.android.data.db.dao.CachedBookDao
import com.bookhaven.android.data.db.dao.DownloadedBookDao
import com.bookhaven.android.data.db.dao.ReadingProgressDao
import com.bookhaven.android.data.db.entity.CachedBook
import com.bookhaven.android.data.db.entity.DownloadedBook
import com.bookhaven.android.data.db.entity.ReadingProgress

@Database(
    entities = [DownloadedBook::class, ReadingProgress::class, CachedBook::class],
    version = 4,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun downloadedBookDao(): DownloadedBookDao
    abstract fun readingProgressDao(): ReadingProgressDao
    abstract fun cachedBookDao(): CachedBookDao

    companion object {
        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL(
                    "ALTER TABLE reading_progress ADD COLUMN progress REAL NOT NULL DEFAULT 0"
                )
            }
        }

        val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL(
                    "CREATE TABLE IF NOT EXISTS cached_books (" +
                        "id INTEGER NOT NULL PRIMARY KEY, " +
                        "title TEXT NOT NULL, " +
                        "author TEXT NOT NULL, " +
                        "format TEXT NOT NULL, " +
                        "category TEXT NOT NULL)"
                )
            }
        }

        val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL(
                    "ALTER TABLE reading_progress ADD COLUMN pending_sync INTEGER NOT NULL DEFAULT 0"
                )
            }
        }
    }
}
