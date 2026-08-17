package com.bookhaven.android.data.db.dao

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.bookhaven.android.data.db.entity.DownloadedBook
import kotlinx.coroutines.flow.Flow

@Dao
interface DownloadedBookDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(book: DownloadedBook)

    @Delete
    suspend fun delete(book: DownloadedBook)

    @Query("SELECT * FROM downloaded_books ORDER BY downloadedAt DESC")
    fun observeAll(): Flow<List<DownloadedBook>>

    @Query("SELECT * FROM downloaded_books ORDER BY downloadedAt DESC")
    suspend fun getAll(): List<DownloadedBook>

    @Query("SELECT * FROM downloaded_books WHERE bookId = :bookId LIMIT 1")
    suspend fun getById(bookId: Int): DownloadedBook?
}
