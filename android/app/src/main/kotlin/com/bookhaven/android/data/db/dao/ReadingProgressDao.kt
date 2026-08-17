package com.bookhaven.android.data.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.bookhaven.android.data.db.entity.ReadingProgress

@Dao
interface ReadingProgressDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(progress: ReadingProgress)

    @Query("SELECT * FROM reading_progress WHERE bookId = :bookId LIMIT 1")
    suspend fun getById(bookId: Int): ReadingProgress?

    @Query("SELECT * FROM reading_progress")
    suspend fun getAll(): List<ReadingProgress>

    @Query("SELECT * FROM reading_progress WHERE pending_sync = 1")
    suspend fun getPending(): List<ReadingProgress>

    @Query("DELETE FROM reading_progress WHERE bookId = :bookId")
    suspend fun deleteById(bookId: Int)
}
